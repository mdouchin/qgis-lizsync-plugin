"""
/***************************************************************************
 Lizsync
                                 A QGIS plugin
 France only - Plugin dedicated to import and manage water network data by using Lizsync standard
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2018-12-19
        copyright            : (C) 2018 by 3liz
        email                : info@3liz.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

__author__ = '3liz'
__date__ = '2018-12-19'
__copyright__ = '(C) 2018 by 3liz'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'

import os
import sys
import inspect

from qgis.core import QgsApplication
from .processing.provider import LizsyncProvider

cmd_folder = os.path.split(inspect.getfile(inspect.currentframe()))[0]

if cmd_folder not in sys.path:
    sys.path.insert(0, cmd_folder)

from qgis.PyQt.QtCore import Qt, QCoreApplication, QTranslator
from .qgis_plugin_tools.tools.i18n import setup_translation
from .qgis_plugin_tools.tools.resources import plugin_path
from .lizsync_dockwidget import LizsyncDockWidget


class LizsyncPlugin:

    def __init__(self, iface):
        self.provider = None
        self.dock = None
        self.iface = iface

        locale, file_path = setup_translation(
            folder=plugin_path("i18n"), file_pattern="lizsync_{}.qm")
        if file_path:
            # LOGGER.info('Translation to {}'.format(file_path))
            self.translator = QTranslator()
            self.translator.load(file_path)
            QCoreApplication.installTranslator(self.translator)
        else:
            # LOGGER.info('Translation not found: {}'.format(locale))
            pass

    def initProcessing(self):
        self.provider = LizsyncProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        self.initProcessing()
        self.dock = LizsyncDockWidget(self.iface)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock)

    def unload(self):
        self.iface.removeDockWidget(self.dock)
        self.dock.deleteLater()
        QgsApplication.processingRegistry().removeProvider(self.provider)
