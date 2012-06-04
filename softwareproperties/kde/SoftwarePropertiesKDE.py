#!/usr/bin/python
# -*- coding: utf-8 -*-
#  Qt 4 based frontend to software-properties
#
#  Copyright (c) 2007 Canonical Ltd.
#
#  Author: Jonathan Riddell <jriddell@ubuntu.com>
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License as
#  published by the Free Software Foundation; either version 2 of the
#  License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307
#  USA

import apt
import apt_pkg
import tempfile
from gettext import gettext as _
import os
import re
from xml.sax.saxutils import escape

import sys
import traceback

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic

import softwareproperties
import softwareproperties.distro
from softwareproperties.SoftwareProperties import SoftwareProperties
import softwareproperties.SoftwareProperties
from aptsources.sourceslist import SourceEntry
from DialogEdit import DialogEdit
from DialogMirror import DialogMirror
from CdromProgress import CdromProgress

class SoftwarePropertiesKDEUI(QWidget):

    def __init__(self, datadir):
        QWidget.__init__(self)
        uic.loadUi("%s/designer/main.ui" % datadir, self)

class SoftwarePropertiesKDE(SoftwareProperties):
  def __init__(self, datadir=None, options=None, parent=None, file=None):
    """ Provide a KDE (actually Qt 4) based graphical user interface to configure
        the used software repositories, corresponding authentication keys
        and update automation """
    SoftwareProperties.__init__(self, options=options, datadir=datadir)

    self.options = options
    self.datadir = datadir

    self.app = QApplication([])

    self.userinterface = SoftwarePropertiesKDEUI(datadir)
    self.userinterface.setWindowIcon(QIcon("/usr/share/icons/hicolor/128x128/apps/adept_manager.png"))
    self.translate_widgets()
    self.userinterface.show()

    sys.excepthook = self.excepthook

    # rejected() signal from Close button
    self.app.connect(self.userinterface.buttonBox, SIGNAL("rejected()"), self.on_close_button)

    self.userinterface.buttonBox.button(QDialogButtonBox.Reset).setEnabled(False)

    # Put some life into the user interface:
    self.init_server_chooser()
    self.init_popcon()
    self.init_auto_update()
    self.show_auto_update_level()
    # Setup the key list
    self.init_keys()
    self.show_keys()
    # Setup the ISV sources list
    self.init_isv_sources()
    self.show_isv_sources()
    self.show_cdrom_sources()

    self.app.connect(self.userinterface.checkbutton_source_code, SIGNAL("clicked()"), self.on_checkbutton_source_code_toggled)
    self.app.connect(self.userinterface.button_auth_restore, SIGNAL("clicked()"), self.on_restore_clicked)
    self.app.connect(self.userinterface.button_add_auth, SIGNAL("clicked()"), self.add_key_clicked)
    self.app.connect(self.userinterface.button_auth_remove, SIGNAL("clicked()"), self.remove_key_clicked)
    self.app.connect(self.userinterface.checkbutton_popcon, SIGNAL("toggled(bool)"), self.on_checkbutton_popcon_toggled)
    self.app.connect(self.userinterface.checkbutton_auto_update, SIGNAL("toggled(bool)"), self.on_auto_update_toggled)
    self.app.connect(self.userinterface.combobox_update_interval, SIGNAL("currentIndexChanged(int)"), self.on_combobox_update_interval_changed)
    self.app.connect(self.userinterface.button_remove, SIGNAL("clicked()"), self.on_remove_clicked)
    self.app.connect(self.userinterface.button_edit, SIGNAL("clicked()"), self.on_edit_clicked)
    self.app.connect(self.userinterface.button_add_cdrom, SIGNAL("clicked()"), self.on_button_add_cdrom_clicked)
    self.app.connect(self.userinterface.button_add, SIGNAL("clicked()"), self.on_add_clicked)
    self.app.connect(self.userinterface.treeview_sources, SIGNAL("itemChanged(QTreeWidgetItem*, int)"), self.on_isv_source_toggled)
    self.app.connect(self.userinterface.treeview_cdroms, SIGNAL("itemChanged(QTreeWidgetItem*, int)"), self.on_cdrom_source_toggled)
    self.app.connect(self.userinterface.treeview_sources, SIGNAL("itemClicked(QTreeWidgetItem*, int)"), self.on_treeview_sources_cursor_changed)
    button_revert = self.userinterface.buttonBox.button(QDialogButtonBox.Reset)
    self.app.connect(button_revert, SIGNAL("clicked()"), self.on_button_revert_clicked)

    self.init_distro()
    self.show_distro()

  def translate_widgets(self):
      """translate the whole user interface"""
      self.translate_widget_children(self.userinterface)

  def translate_widget_children(self, parentWidget):
      """translate given widget and its children"""
      for widget in parentWidget.children():
          self.translate_widget(widget)
          self.translate_widget_children(widget)

  def translate_widget(self, widget):
      """translate the text on a widget"""
      if isinstance(widget, QLabel):
          text = str(widget.text())
          text = _(text)
          ##FIXME string is a str but in unicode.  PyQt thinks it isn't unicode and any non-ascii characters break, how to fix??
          text = unicode(text, 'utf-8')
          widget.setText(text)
      elif isinstance(widget, QPushButton):
          text = str(widget.text())
          text = _(text)
          text = unicode(text, 'utf-8')
          widget.setText(text)
      elif isinstance(widget, QGroupBox):
          text = str(widget.title())
          text = _(text)
          text = unicode(text, 'utf-8')
          widget.setTitle(text)
      elif isinstance(widget, QCheckBox):
          text = str(widget.text())
          text = _(text)
          text = unicode(text, 'utf-8')
          widget.setText(text)

  def init_popcon(self):
    """ If popcon is enabled show the statistics tab and an explanation
        corresponding to the used distro """
    is_helpful = self.get_popcon_participation()
    if is_helpful != None:
      text = softwareproperties.distro.get_popcon_description(self.distro)
      text = text.replace("\n", "<br />") #silly GTK mixes HTML and normal white space
      self.userinterface.label_popcon_desc.setText(unicode(text, 'UTF-8'))
      self.userinterface.checkbutton_popcon.setChecked(is_helpful)
    else:
      self.userinterface.tabWidget.removeTab(4)

  def init_server_chooser(self):
    """ Set up the widgets that allow to choose an alternate download site """
    # nothing to do here, set up signal in show_distro()
    pass

  def init_auto_update(self):
    """ Set up the widgets that allow to configure the update automation """
    # this maps the key (combo-box-index) to the auto-update-interval value
    # where (-1) means, no key
    self.combobox_interval_mapping = { 0 : 1,
                                       1 : 2,
                                       2 : 7,
                                       3 : 14 }

    self.userinterface.combobox_update_interval.insertItem(99, unicode(_("Daily"), 'utf-8'))
    self.userinterface.combobox_update_interval.insertItem(99, unicode(_("Every two days"), 'utf-8'))
    self.userinterface.combobox_update_interval.insertItem(99, unicode(_("Weekly"), 'utf-8'))
    self.userinterface.combobox_update_interval.insertItem(99, unicode(_("Every two weeks"), 'utf-8'))

    update_days = self.get_update_interval()

    # If a custom period is defined add a corresponding entry
    if not update_days in self.combobox_interval_mapping.values():
        if update_days > 0:
            self.userinterface.combobox_update_interval.insertItem(99, unicode(_("Every %s days"), 'utf-8') % update_days)
            self.combobox_interval_mapping[4] = update_days

    for key in self.combobox_interval_mapping:
      if self.combobox_interval_mapping[key] == update_days:
        self.userinterface.combobox_update_interval.setCurrentIndex(key)
        break

    if update_days >= 1:
      self.userinterface.checkbutton_auto_update.setChecked(True)
      self.userinterface.combobox_update_interval.setEnabled(True)
      self.userinterface.radiobutton_updates_inst_sec.setEnabled(True)
      self.userinterface.radiobutton_updates_download.setEnabled(True)
      self.userinterface.radiobutton_updates_notify.setEnabled(True)
    else:
      self.userinterface.checkbutton_auto_update.setChecked(False)
      self.userinterface.combobox_update_interval.setEnabled(False)
      self.userinterface.radiobutton_updates_inst_sec.setEnabled(False)
      self.userinterface.radiobutton_updates_download.setEnabled(False)
      self.userinterface.radiobutton_updates_notify.setEnabled(False)

    self.app.connect(self.userinterface.radiobutton_updates_download, SIGNAL("toggled(bool)"), self.set_update_automation_level)
    self.app.connect(self.userinterface.radiobutton_updates_inst_sec, SIGNAL("toggled(bool)"), self.set_update_automation_level)
    self.app.connect(self.userinterface.radiobutton_updates_notify, SIGNAL("toggled(bool)"), self.set_update_automation_level)

  def show_auto_update_level(self):
    """Represent the level of update automation in the user interface"""
    level = self.get_update_automation_level()
    if level == None:
        self.userinterface.radiobutton_updates_inst_sec.setChecked(False)
        self.userinterface.radiobutton_updates_download.setChecked(False)
        self.userinterface.radiobutton_updates_notify.setChecked(False)
    if level == softwareproperties.UPDATE_MANUAL or\
       level == softwareproperties.UPDATE_NOTIFY:
        self.userinterface.radiobutton_updates_notify.setChecked(True)
    elif level == softwareproperties.UPDATE_DOWNLOAD:
        self.userinterface.radiobutton_updates_download.setChecked(True)
    elif level == softwareproperties.UPDATE_INST_SEC:
        self.userinterface.radiobutton_updates_inst_sec.setChecked(True)

  def init_distro(self):
    # TRANS: %s stands for the distribution name e.g. Debian or Ubuntu
    text = "<b>%s</b>" % (_("%s updates") % self.distro.id)
    text = text.replace("Ubuntu", "Kubuntu")
    self.userinterface.label_updates.setText(unicode(text, 'UTF-8'))
    # TRANS: %s stands for the distribution name e.g. Debian or Ubuntu
    text = _("%s Software") % self.distro.id
    text = unicode(text, 'utf-8')
    text = text.replace("Ubuntu", "Kubuntu")
    self.userinterface.tabWidget.setTabText(0, text)

    # Setup the checkbuttons for the components
    for child in self.userinterface.vbox_dist_comps_frame.children():
        if isinstance(child, QGridLayout):
            self.vbox_dist_comps = child
        else:
            child.hide()
            del child
    self.checkboxComps = {}
    for comp in self.distro.source_template.components:
        # TRANSLATORS: Label for the components in the Internet section
        #              first %s is the description of the component
        #              second %s is the code name of the comp, eg main, universe
        label = _("%s (%s)") % (comp.get_description(), comp.name)
        checkbox = QCheckBox(unicode(label, 'utf-8'), self.userinterface.vbox_dist_comps_frame)
        checkbox.setObjectName(comp.name)
        self.checkboxComps[checkbox] = comp

        # setup the callback and show the checkbutton
        self.app.connect(checkbox, SIGNAL("clicked()"), self.on_component_toggled)
        self.vbox_dist_comps.addWidget(checkbox)

    # Setup the checkbuttons for the child repos / updates
    for child in self.userinterface.vbox_updates_frame.children():
        if isinstance(child, QGridLayout):
            self.vbox_updates = child
        else:
            del child
    if len(self.distro.source_template.children) < 1:
        self.userinterface.vbox_updates_frame.hide()
    self.checkboxTemplates = {}
    for template in self.distro.source_template.children:
        checkbox = QCheckBox(unicode(template.description, 'utf-8'), self.userinterface.vbox_updates_frame)
        checkbox.setObjectName(template.name)
        self.checkboxTemplates[checkbox] = template
        # setup the callback and show the checkbutton
        self.app.connect(checkbox, SIGNAL("clicked()"), self.on_checkbutton_child_toggled)
        self.vbox_updates.addWidget(checkbox)

    # If no components are enabled there will be no need for updates
    if len(self.distro.enabled_comps) < 1:
        self.userinterface.vbox_updates_frame.setEnabled(False)
    else:
        self.userinterface.vbox_updates_frame.setEnabled(True)

    # Intiate the combobox which allows the user to specify a server for all
    # distro related sources
    seen_server_new = []
    self.mirror_urls = []
    for (name, uri, active) in self.distro.get_server_list():
        ##server_store.append([name, uri, False])
        self.userinterface.combobox_server.addItem(name)
        self.mirror_urls.append(uri)
        if [name, uri] in self.seen_server:
            self.seen_server.remove([name, uri])
        elif uri != None:
            seen_server_new.append([name, uri])
        if active == True:
            self.active_server = self.userinterface.combobox_server.count() - 1
            self.userinterface.combobox_server.setCurrentIndex(self.userinterface.combobox_server.count() - 1)
    for [name, uri] in self.seen_server:
        self.userinterface.combobox_server.addItem(name)
    self.seen_server = seen_server_new
    # add a separator and the option to choose another mirror from the list
    ##FIXME server_store.append(["sep", None, True])
    self.userinterface.combobox_server.addItem(unicode(_("Other..."), 'utf-8'))
    self.mirror_urls.append("")

    self.app.connect(self.userinterface.combobox_server, SIGNAL("currentIndexChanged(int)"), self.on_combobox_server_changed)

  def show_distro(self):
    """
    Represent the distro information in the user interface
    """
    # Enable or disable the child source checkbuttons
    for child in self.userinterface.vbox_updates_frame.children():
        if isinstance(child, QCheckBox):
            template = self.checkboxTemplates[child]
            (active, inconsistent) = self.get_comp_child_state(template)
            if inconsistent:
                child.setCheckState(Qt.PartiallyChecked)
            elif active:
                child.setCheckState(Qt.Checked)
            else:
                child.setCheckState(Qt.Unchecked)

    # Enable or disable the component checkbuttons
    for child in self.userinterface.vbox_dist_comps_frame.children():
        if isinstance(child, QCheckBox):
            template = self.checkboxComps[child]
            (active, inconsistent) = self.get_comp_download_state(template)
            if inconsistent:
                child.setCheckState(Qt.PartiallyChecked)
            elif active:
                child.setCheckState(Qt.Checked)
            else:
                child.setCheckState(Qt.Unchecked)

    # If no components are enabled there will be no need for updates
    # and source code
    if len(self.distro.enabled_comps) < 1:
        self.userinterface.vbox_updates_frame.setEnabled(False)
        self.userinterface.checkbutton_source_code.setEnabled(False)
    else:
        self.userinterface.vbox_updates_frame.setEnabled(True)
        self.userinterface.checkbutton_source_code.setEnabled(True)

    # Check for source code sources
    source_code_state = self.get_source_code_state()
    if source_code_state == True:
        self.userinterface.checkbutton_source_code.setCheckState(Qt.Checked)
    elif source_code_state == None:
        self.userinterface.checkbutton_source_code.setCheckState(Qt.PartiallyChecked)
    else:
        self.userinterface.checkbutton_source_code.setCheckState(Qt.Unchecked)

    # Will show a short explanation if no CDROMs are used
    if len(self.get_cdrom_sources()) == 0:
        self.userinterface.treeview_cdroms.hide()
        self.userinterface.textview_no_cd.show()
        self.userinterface.groupBox_cdrom.hide()
    else:
        self.userinterface.treeview_cdroms.show()
        self.userinterface.textview_no_cd.hide()
        self.userinterface.groupBox_cdrom.show()

    # Output a lot of debug stuff
    if self.options.debug == True or self.options.massive_debug == True:
        print "ENABLED COMPS: %s" % self.distro.enabled_comps
        print "INTERNET COMPS: %s" % self.distro.download_comps
        print "MAIN SOURCES"
        for source in self.distro.main_sources:
            self.print_source_entry(source)
        print "CHILD SOURCES"
        for source in self.distro.child_sources:
            self.print_source_entry(source)
        print "CDROM SOURCES"
        for source in self.distro.cdrom_sources:
            self.print_source_entry(source)
        print "SOURCE CODE SOURCES"
        for source in self.distro.source_code_sources:
            self.print_source_entry(source)
        print "DISABLED SOURCES"
        for source in self.distro.disabled_sources:
            self.print_source_entry(source)
        print "ISV"
        for source in self.sourceslist_visible:
            self.print_source_entry(source)

  def set_update_automation_level(self, selected):
    """Call the backend to set the update automation level to the given 
       value"""
    if self.userinterface.radiobutton_updates_download.isChecked():
        SoftwareProperties.set_update_automation_level(self, softwareproperties.UPDATE_DOWNLOAD)
    elif self.userinterface.radiobutton_updates_inst_sec.isChecked():
        SoftwareProperties.set_update_automation_level(self, softwareproperties.UPDATE_INST_SEC)
    elif self.userinterface.radiobutton_updates_notify.isChecked():
        SoftwareProperties.set_update_automation_level(self, softwareproperties.UPDATE_NOTIFY)
    self.set_modified_config()

  def on_combobox_server_changed(self, combobox):
    """
    Replace the servers used by the main and update sources with
    the selected one
    """
    combobox = self.userinterface.combobox_server
    if combobox.currentIndex() == self.active_server:
        return
    uri = self.mirror_urls[combobox.currentIndex()]
    name = unicode(combobox.currentText())
    if name == unicode(_("Other..."), 'utf-8'):
        dialogue = DialogMirror(self.userinterface, self.datadir, self.distro, self.custom_mirrors)
        self.translate_widget_children(dialogue)
        res = dialogue.run()
        if res != None:
            self.distro.change_server(res)
            self.set_modified_sourceslist()
            ##FIXME insert new URL into combo box
        else:
            combobox.setCurrentIndex(self.active_server)
    elif uri != None and len(self.distro.used_servers) > 0:
        self.active_server = combobox.currentIndex()
        self.distro.change_server(uri)
        self.set_modified_sourceslist()
    else:
        self.distro.default_server = uri

  def on_component_toggled(self):
    """
    Sync the components of all main sources (excluding cdroms),
    child sources and source code sources
    """
    tickBox = self.app.sender()
    if tickBox.checkState() == Qt.Checked:
        self.enable_component(str(tickBox.objectName()))
    elif tickBox.checkState() == Qt.Unchecked:
        self.disable_component(str(tickBox.objectName()))
    self.set_modified_sourceslist()

    # no way to set back to mixed state so turn off tristate
    tickBox.setTristate(False)

  def on_checkbutton_child_toggled(self):
    """
    Enable or disable a child repo of the distribution main repository
    """
    tickBox = self.app.sender()
    name = str(tickBox.objectName())
    for template in self.distro.source_template.children:
        if name == template.name:
            aptTemplate = template

    if tickBox.checkState() == Qt.Checked:
        self.enable_child_source(aptTemplate)
    elif tickBox.checkState() == Qt.Unchecked:
        self.disable_child_source(aptTemplate)
    # no way to set back to mixed state so turn off tristate
    tickBox.setTristate(False)

  def on_checkbutton_source_code_toggled(self):
    """ Disable or enable the source code for all sources """
    if self.userinterface.checkbutton_source_code.checkState() == Qt.Checked:
        self.enable_source_code_sources()
    elif self.userinterface.checkbutton_source_code.checkState() == Qt.Unchecked:
        self.disable_source_code_sources()
    self.userinterface.checkbutton_source_code.setTristate(False)

  def on_checkbutton_popcon_toggled(self, state):
    """ The user clicked on the popcon paritipcation button """
    self.set_popcon_pariticipation(state)

  def init_isv_sources(self):
    """Read all valid sources into our ListStore"""
    self.userinterface.treeview_cdroms.setHeaderLabel(unicode(_("Software Sources"), 'utf-8'))
    self.userinterface.treeview_sources.setHeaderLabel(unicode(_("Software Sources"), 'utf-8'))

    """##FIXME
    # drag and drop support for sources.list
    self.treeview_sources.drag_dest_set(gtk.DEST_DEFAULT_ALL, \
                                        [('text/uri-list',0, 0)], \
                                        gtk.gdk.ACTION_COPY)
    self.treeview_sources.connect("drag_data_received",\
                                  self.on_sources_drag_data_received)
    """

  def on_isv_source_activate(self, treeview, path, column):
    """Open the edit dialog if a channel was double clicked"""
    ##FIXME TODO
    ##self.on_edit_clicked(treeview)

  def on_treeview_sources_cursor_changed(self, item, column):
    """set the sensitiveness of the edit and remove button
       corresponding to the selected channel"""
    # allow to remove the selected channel
    self.userinterface.button_remove.setEnabled(True)
    # disable editing of cdrom sources
    index = self.userinterface.treeview_sources.indexOfTopLevelItem(item)
    source_entry = self.isv_sources[index]
    if source_entry.uri.startswith("cdrom:"):
        self.userinterface.button_edit.setEnabled(False)
    else:
        self.userinterface.button_edit.setEnabled(True)

  def on_cdrom_source_toggled(self, item):
    """Enable or disable the selected channel"""
    index = self.userinterface.treeview_cdroms.indexOfTopLevelItem(item)
    source_entry = self.cdrom_sources[index]
    self.toggle_source_use(source_entry)

  def on_isv_source_toggled(self, item):
    """Enable or disable the selected channel"""
    index = self.userinterface.treeview_sources.indexOfTopLevelItem(item)
    source_entry = self.isv_sources[index]
    self.toggle_source_use(source_entry)

  def init_keys(self):
    """Setup the user interface parts needed for the key handling"""
    self.userinterface.treeview2.setColumnCount(1)
    self.userinterface.treeview2.setHeaderLabels([unicode(_("Key"), 'utf-8')])

  #FIXME revert automation settings too
  def on_button_revert_clicked(self):
    """Restore the source list from the startup of the dialog"""
    SoftwareProperties.revert(self)
    self.set_modified_sourceslist()
    self.show_auto_update_level()
    self.userinterface.buttonBox.button(QDialogButtonBox.Reset).setEnabled(False)
    self.modified_sourceslist = False

  def set_modified_config(self):
    """The config was changed and now needs to be saved and reloaded"""
    SoftwareProperties.set_modified_config(self)
    self.userinterface.buttonBox.button(QDialogButtonBox.Reset).setEnabled(True)

  def set_modified_sourceslist(self):
    """The sources list was changed and now needs to be saved and reloaded"""
    SoftwareProperties.set_modified_sourceslist(self)
    self.show_distro()
    self.show_isv_sources()
    self.show_cdrom_sources()
    self.userinterface.buttonBox.button(QDialogButtonBox.Reset).setEnabled(True)

  def show_isv_sources(self):
    """ Show the repositories of independent software vendors in the
        third-party software tree view """
    self.userinterface.treeview_sources.clear()
    self.isv_sources = []

    for source in self.get_isv_sources():
        contents = self.render_source(source)
        contents = contents.replace("<b>", "")
        contents = contents.replace("</b>", "")
        item = QTreeWidgetItem([contents])
        if not source.disabled:
            item.setCheckState(0, Qt.Checked)
        else:
            item.setCheckState(0, Qt.Unchecked)
        self.userinterface.treeview_sources.addTopLevelItem(item)
        self.isv_sources.append(source)

    if self.userinterface.treeview_sources.topLevelItemCount() < 1:
        self.userinterface.button_remove.setEnabled(False)
        self.userinterface.button_edit.setEnabled(False)

  def show_cdrom_sources(self):
    """ Show CD-ROM/DVD based repositories of the currently used distro in
        the CDROM based sources list """
    self.userinterface.treeview_cdroms.clear()
    self.cdrom_sources = []

    for source in self.get_cdrom_sources():
        contents = self.render_source(source)
        contents = contents.replace("<b>", "")
        contents = contents.replace("</b>", "")
        item = QTreeWidgetItem([contents])
        if not source.disabled:
            item.setCheckState(0, Qt.Checked)
        else:
            item.setCheckState(0, Qt.Unchecked)
        self.userinterface.treeview_cdroms.addTopLevelItem(item)
        self.cdrom_sources.append(source)
    
  def show_keys(self):
    self.userinterface.treeview2.clear()
    for key in self.apt_key.list():
      self.userinterface.treeview2.addTopLevelItem(QTreeWidgetItem([unicode(key, 'UTF-8')]))

  def on_combobox_update_interval_changed(self, index):
    #FIXME! move to backend
    if index != -1:
        value = self.combobox_interval_mapping[index]
        # Only write the key if it has changed
        if not value == apt_pkg.Config.FindI(softwareproperties.CONF_MAP["autoupdate"]):
            apt_pkg.Config.Set(softwareproperties.CONF_MAP["autoupdate"], str(value))
            self.write_config()

  def on_auto_update_toggled(self):
    """Enable or disable automatic updates and modify the user interface
       accordingly"""
    if self.userinterface.checkbutton_auto_update.checkState() == Qt.Checked:
      self.userinterface.combobox_update_interval.setEnabled(True)
      self.userinterface.radiobutton_updates_inst_sec.setEnabled(True)
      self.userinterface.radiobutton_updates_download.setEnabled(True)
      self.userinterface.radiobutton_updates_notify.setEnabled(True)
      # if no frequency was specified use daily
      i = self.userinterface.combobox_update_interval.currentIndex()
      if i == -1:
          i = 0
          self.userinterface.combobox_update_interval.setCurrentIndex(i)
      value = self.combobox_interval_mapping[i]
    else:
      self.userinterface.combobox_update_interval.setEnabled(False)
      self.userinterface.radiobutton_updates_inst_sec.setEnabled(False)
      self.userinterface.radiobutton_updates_download.setEnabled(False)
      self.userinterface.radiobutton_updates_notify.setEnabled(False)
      SoftwareProperties.set_update_automation_level(self, None)
      value = 0
    self.set_update_interval(str(value))

  def on_add_clicked(self):
    """Show a dialog that allows to enter the apt line of a to be used repo"""
    if self.distro:
        example = "%s %s %s %s" % (self.distro.binary_type,
                                   self.distro.source_template.base_uri,
                                   self.distro.codename,
                                   self.distro.source_template.components[0].name)
    else:
        example = "deb http://ftp.debian.org sarge main"
    # L10N: the example is of the format: deb http://ftp.debian.org sarge main
    text = _('<p><b>Enter the complete APT line of the<br /> repository that you want to add as source</b></p><p>The APT line includes the type, location and components of a repository,<br /> for example <i>"%s"</i>.</p>' % example)
    (line, valid) = QInputDialog.getText(self.userinterface, unicode(_("Add APT repository"), 'utf-8'), text)
    uline = unicode(line)
    if valid:
        self.add_source_from_line(uline)
        self.show_isv_sources()

  def on_edit_clicked(self):
    """Show a dialog to edit an ISV source"""
    item = self.userinterface.treeview_sources.currentItem()
    if item is not None:
        index = self.userinterface.treeview_sources.indexOfTopLevelItem(item)
        dialogue = DialogEdit(self.userinterface, self.sourceslist, self.isv_sources[index], self.datadir)
        self.translate_widget_children(dialogue)
        result = dialogue.run()
        if result == QDialog.Accepted:
            self.set_modified_sourceslist()
            self.show_isv_sources()

  # FIXME:outstanding from merge
  def on_isv_source_activated(self, treeview, path, column):
     """Open the edit dialog if a channel was double clicked"""
     ##FIXME TODO
     # check if the channel can be edited
     if self.button_edit.get_property("sensitive") == True:
         self.on_edit_clicked(treeview)

  def on_remove_clicked(self):
    """Remove the selected source"""
    item = self.userinterface.treeview_sources.currentItem()
    if item is not None:
        index = self.userinterface.treeview_sources.indexOfTopLevelItem(item)
        self.remove_source(self.isv_sources[index])
        self.show_isv_sources()

  def add_key_clicked(self):
    """Provide a file chooser that allows to add the gnupg of a trusted
       software vendor"""
    filename = QFileDialog.getOpenFileName(self.userinterface, unicode(_("Import key"), 'utf-8'))
    if filename is not None:
      if not self.add_key(filename):
        title = _("Error importing selected file")
        text = _("The selected file may not be a GPG key file " \
                "or it might be corrupt.")
        QMessageBox.warning(self.userinterface,
              unicode(title, 'utf-8'),
              unicode(text, 'utf-8'))
      self.show_keys()

  def remove_key_clicked(self):
    """Remove a trusted software vendor key"""
    item = self.userinterface.treeview2.currentItem()
    if item == None:
        return
    key = item.text(0)
    if self.remove_key(key[:8]):
      title = _("Error removing the key")
      text = _("The key you selected could not be removed. "
               "Please report this as a bug.")
      QMessageBox.warning(self.userinterface, unicode(title, 'utf-8'), unicode(text, 'utf-8'))
    self.show_keys()

  def on_restore_clicked(self):
    """Restore the original keys"""
    self.apt_key.update()
    self.show_keys()

  def on_close_button(self):
    """Show a dialog that a reload of the channel information is required
       only if there is no parent defined"""
    if self.modified_sourceslist == True and self.options.toplevel == None:
        messageBox = QMessageBox(self.userinterface)
        messageBox.setIcon(QMessageBox.Information)
        messageBox.addButton(unicode(_("Reload"), 'utf-8'), QMessageBox.YesRole)
        messageBox.addButton(unicode(_("Close"), 'utf-8'), QMessageBox.NoRole)
        text = _("<b><big>The information about available software is out-of-date</big></b>\n"
               "\n"
               "To install software and updates from newly added or changed sources, you "
               "have to reload the information about available software.\n"
               "\n"
               "You need a working internet connection to continue.")
        text = text.replace("\n", "<br />")
        messageBox.setText(unicode(text, 'utf-8'))
        messageBox.exec_()
        ##FIXME tell adept to reload package cache
    self.app.quit()

  def on_button_add_cdrom_clicked(self):
    '''Show a dialog that allows to add a repository located on a CDROM
       or DVD'''
    # testing
    #apt_pkg.Config.Set("APT::CDROM::Rename","true")

    saved_entry = apt_pkg.Config.Find("Dir::Etc::sourcelist")
    tmp = tempfile.NamedTemporaryFile()
    apt_pkg.Config.Set("Dir::Etc::sourcelist",tmp.name)
    progress = CdromProgress(self.datadir, self)
    cdrom = apt_pkg.GetCdrom()
    # if nothing was found just return
    try:
      res = cdrom.Add(progress)
    except SystemError, msg:
      progress.close()
      title = _("CD Error")
      text = _("<big><b>Error scanning the CD</b></big>\n\n%s")%msg
      QMessageBox.warning(self.userinterface, unicode(title, 'utf-8'), unicode(text, 'utf-8'))
      return
    apt_pkg.Config.Set("Dir::Etc::sourcelist",saved_entry)
    if res == False:
      progress.close()
      return
    # read tmp file with source name (read only last line)
    line = ""
    for x in open(tmp.name):
      line = x
    if line != "":
      full_path = "%s%s" % (apt_pkg.Config.FindDir("Dir::Etc"),saved_entry)
      self.sourceslist.list.append(SourceEntry(line,full_path))
      self.set_modified_sourceslist()

  def run(self):
    self.app.exec_()

  def excepthook(self, exctype, excvalue, exctb):
      """Crash handler."""
      print "excepthook"

      if (issubclass(exctype, KeyboardInterrupt) or
          issubclass(exctype, SystemExit)):
          return

      tbtext = ''.join(traceback.format_exception(exctype, excvalue, exctb))
      dialog = QDialog(self.userinterface)
      uic.loadUi("%s/designer/crashdialog.ui" % self.datadir, dialog)
      dialog.beastie_url.setOpenExternalLinks(True)
      dialog.crash_detail.setText(tbtext)
      dialog.exec_()
      sys.exit(1)
