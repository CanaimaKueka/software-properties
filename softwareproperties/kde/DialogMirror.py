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
import threading
import random

from softwareproperties.MirrorTest import MirrorTest

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic

from softwareproperties.CountryInformation import CountryInformation

def threaded(f):
    ''' Thanks to Ross Burton for this piece of code '''
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=f, args=args, kwargs=kwargs)
        t.setDaemon(True)
        t.start()
    wrapper.__name__ = f.__name__
    return wrapper

class DialogMirror(QDialog):

  def __init__(self, parent, datadir, distro, custom_mirrors):
    """
    Initialize the dialog that allows to choose a custom or official mirror
    """
    QDialog.__init__(self, parent)
    uic.loadUi("%s/designer/dialog_mirror.ui" % datadir, self)
    self.parent = parent

    self.custom_mirrors = custom_mirrors

    self.country_info = CountryInformation()

    self.button_choose = self.buttonBox.button(QDialogButtonBox.Ok)
    self.button_choose.setEnabled(False)
    self.button_cancel = self.buttonBox.button(QDialogButtonBox.Cancel)
    self.distro = distro

    self.treeview.setColumnCount(1)
    self.treeview.setHeaderLabels([_("Mirror")])

    # used to find the corresponding iter of a location
    map_loc = {}
    patriot = None
    """ no custom yet
    # at first add all custom mirrors and a separator
    if len(self.custom_mirrors) > 0:
        for mirror in self.custom_mirrors:

            model.append(None, [mirror, False, True, None])
            self.column_mirror.add_attribute(self.renderer_mirror, 
                                             "editable", 
                                             COLUMN_CUSTOM)
        model.append(None, [None, True, False, None])
    """
    self.mirror_map = {}
    # secondly add all official mirrors
    for hostname in self.distro.source_template.mirror_set.keys():
        mirror = self.distro.source_template.mirror_set[hostname]
        if map_loc.has_key(mirror.location):  # a mirror in a country
            QTreeWidgetItem(map_loc[mirror.location], [hostname])
            self.mirror_map[hostname] = mirror
        elif mirror.location != None:  # a country new to the list
            country = self.country_info.get_country_name(mirror.location)
            parent = QTreeWidgetItem([unicode(country, 'utf-8')])
            self.mirror_map[country] = None
            self.treeview.addTopLevelItem(parent)
            QTreeWidgetItem(parent, [hostname])
            self.mirror_map[hostname] = mirror
            if mirror.location == self.country_info.code and patriot == None:
                patriot = parent
            map_loc[mirror.location] = parent
        else:  # a mirror without country
            item = QTreeWidgetItem([hostname])
            self.treeview.addTopLevelItem(item)
    # Scroll to the local mirror set
    if patriot != None:
        self.treeview.scrollToItem(patriot)
    self.treeview.sortItems(0, Qt.AscendingOrder)
    self.connect(self.treeview, SIGNAL("itemClicked(QTreeWidgetItem*, int)"), self.on_treeview_mirrors_cursor_changed)
    self.connect(self.button_find_server, SIGNAL("clicked()"), self.on_button_test_clicked)
    self.edit_buttons_frame.hide()  ##FIXME not yet implemented

  def on_treeview_mirrors_cursor_changed(self, item, column):
    """ Check if the currently selected row in the mirror list
        contains a mirror and or is editable """
    # Update the list of available protocolls
    hostname = unicode(self.treeview.currentItem().text(0))
    mirror = self.mirror_map[hostname]
    self.combobox.clear()
    if mirror != None:
        self.combobox.setEnabled(True)
        seen_protos = []
        self.protocol_paths = {}
        for repo in mirror.repositories:
            # Only add a repository for a protocoll once
            if repo.proto in seen_protos:
                continue
            seen_protos.append(repo.proto)
            self.protocol_paths[repo.get_info()[0]] = repo.get_info()[1]
            self.combobox.addItem(repo.get_info()[0])
        self.button_choose.setEnabled(True)
    else:
        self.button_choose.setEnabled(False)
    """
        # Allow to edit and remove custom mirrors
        self.button_remove.set_sensitive(model.get_value(iter, COLUMN_CUSTOM))
        self.button_edit.set_sensitive(model.get_value(iter, COLUMN_CUSTOM))
        self.button_choose.set_sensitive(self.is_valid_mirror(model.get_value(iter, COLUMN_URI)))
        self.combobox.set_sensitive(False)

    """

  def run(self):
    """ Run the chooser dialog and return the chosen mirror or None """
    res = self.exec_()

    # FIXME: we should also return the list of custom servers
    if res == QDialog.Accepted:
        text = unicode(self.treeview.currentItem().text(0))
        mirror = self.mirror_map[text]

        if mirror == None:
            # Return the URL of the selected custom mirror
            print "Error, unknown mirror"
            return None
            ##FIXME return model.get_value(iter, COLUMN_URI)
        else:
            # Return a URL created from the hostname and the selected
            # repository
            proto = unicode(self.combobox.currentText())

            directory = self.protocol_paths[proto]
            return "%s://%s/%s" % (proto, mirror.hostname, directory)
    else:
        return None

  @threaded
  def on_button_test_clicked(self):
    ''' Perform a test to find the best mirror and select it 
        afterwards in the treeview '''
    class MirrorTestGtk(MirrorTest):
        def __init__(self, mirrors, test_file, running, dialogue, parent):
            MirrorTest.__init__(self, mirrors, test_file, running)
            self.dialogue = dialogue
            self.parent = parent
        def report_action(self, text):
            ##Qt doesn't like settings text in a thread
            #gtk.gdk.threads_enter()
            #self.label.set_label(str("<i>%s</i>" % text))
            #gtk.gdk.threads_leave()
            #self.dialogue.setLabelText(str("<i>%s</i>" % text))
            self.parent.process()
            pass
        def report_progress(self, current, max, borders=(0,1), mod=(0,0)):
            ##Qt doesn't like settings text in a thread
            #gtk.gdk.threads_enter()
            #self.progress.set_text(_("Completed %s of %s tests") % \
            #                       (current + mod[0], max + mod[1]))
            #self.dialogue.setLabelText(_("Completed %s of %s tests") % \
            #                       (current + mod[0], max + mod[1]))
            frac = borders[0] + (borders[1] - borders[0]) / max * current
            #self.progress.set_fraction(frac)
            self.dialogue.setValue(frac*100)
            self.parent.process()
            #gtk.gdk.threads_leave()
        def run_full_test(self):
            # Determinate the 5 top ping servers
            results_ping = self.run_ping_test(max=5,
                                              borders=(0, 0.5),
                                              mod=(0,7))
            # Add two random mirrors to the download test
            results_ping.append([0, 0, self.mirrors[random.randint(1, len(self.mirrors))]])
            results_ping.append([0, 0, self.mirrors[random.randint(1, len(self.mirrors))]])
            results = self.run_download_test(map(lambda r: r[2], results_ping),
                                             borders=(0.5, 1),
                                             mod=(MirrorTest.todo,
                                                  MirrorTest.todo))
            for (t, h) in results:
                print h.hostname,t
            if len(results) == 0:
                return None
            else:
                return results[0][1].hostname

    self.dialogue = QProgressDialog(_("Testing Mirrors"), _("Cancel"), 0, 100, self)
    self.dialogue.setWindowTitle(_("Testing Mirrors"))
    self.dialogue.setWindowModality(Qt.WindowModal)
    self.cancelButton = QPushButton(_("Cancel"), self.dialogue)
    self.dialogue.setCancelButton(self.cancelButton)
    self.connect(self.cancelButton, SIGNAL("clicked()"), self.progressCancelled);
    self.cancelButton.setEnabled(False) ##FIXME, cancel doesn't work (because it's in a thread?)
    self.dialogue.show()

    self.running = threading.Event()
    self.running.set()
    pipe = os.popen("dpkg --print-architecture")
    arch = pipe.read().strip()
    test_file = "dists/%s/%s/binary-%s/Packages.gz" % \
                 (self.distro.source_template.name,
                  self.distro.source_template.components[0].name,
                  arch)
    test = MirrorTestGtk(self.distro.source_template.mirror_set.values(),
                         test_file,
                         self.running,
                         self.dialogue, self)
    test.start()
    rocker = test.run_full_test()
    self.dialogue.hide()
    # Select the mirror in the list or show an error dialog
    if rocker != None:
        self.select_mirror(rocker)
    """
    else:
        dialogs.show_error_dialog(self.dialog, 
                                  _("No suitable download server was found"),
                                  _("Please check your Internet connection."))
    """

  def progressCancelled(self):
    pass

  def process(self):
    if self.dialogue.wasCanceled():
        self.running.clear()
    app = QApplication.instance()
    app.processEvents()

  def select_mirror(self, mirror):
    """Select and expand the path to a matching mirror in the list"""
    found = self.treeview.findItems(QString(mirror), Qt.MatchExactly|Qt.MatchRecursive)
    if len(found) > 0:
      found[0].setSelected(True)
      self.treeview.scrollToItem(found[0])
      return True
