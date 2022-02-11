# -*- coding: utf-8 -*-
"""
/***************************************************************************
 uwg_reclassifier
                                 A QGIS plugin
 This Plugin reclassifies vector data into UWG Classes
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2021-11-11
        git sha              : $Format:%H$
        copyright            : (C) 2021 by Oskar Bäcklin & Fredrik Lindberg University of Gothenburg
        email                : oskar.backlin@gu.se
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
from tracemalloc import stop
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import  QgsMapLayerProxyModel, QgsVectorLayer, QgsProject, QgsVectorFileWriter, QgsField, QgsFieldProxyModel
from qgis.PyQt.QtWidgets import QFileDialog, QAction, QMessageBox

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .uwg_reclassifier_dialog import uwg_reclassifierDialog
import os.path
import pandas as pd
from pathlib import Path
import copy
import webbrowser


class uwg_reclassifier(object):
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'uwg_reclassifier_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&UWG Reclassifier')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('uwg_reclassifier', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/uwg_reclassifier/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'UWG Reclassifier'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&UWG Reclassifier'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        # if self.first_start == True:
        #     self.first_start = False
        self.dlg = uwg_reclassifierDialog()      
      
        UWG_types = ['FullServiceRestaurant','Hospital','LargeHotel','LargeOffice','MedOffice',
        'MidRiseApartment','OutPatient','PrimarySchool','QuickServiceRestaurant',
        'SecondarySchool','SmallHotel','SmallOffice','StandAloneRetail','StripMall',
        'SuperMarket','Warehouse']
        
        # self.dlg.comboBoxTypeInfo.addItems(sorted(UWG_types))
        # self.dlg.comboBoxTypeInfo.setCurrentIndex(-1)

        self.dlg.comboBoxVector.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        # self.dlg.comboBoxVector.setFilters(QgsFieldProxyModel.String)

        self.dlg.comboBoxVector.setCurrentIndex(-1)

        self.dlg.comboBoxField.clear()

        for i in range(0,21):
            Oc = eval('self.dlg.lineEdit_' + str(i))
            Oc.clear()
            Oc.setDisabled(True)
            Nc = eval('self.dlg.comboBoxNew_' + str(i))
            Nc.addItems(sorted(UWG_types))
            Nc.setCurrentIndex(-1)
            Nc.setDisabled(True)
            Pr = eval('self.dlg.comboBoxpPeriod_' + str(i))
            Pr.addItems(['Pre80','Pst80','New'])
            Pr.setCurrentIndex(-1)
            Pr.setDisabled(True)

        self.fileDialog = QFileDialog()
        self.dlg.runButton.clicked.connect(self.reclassify_to_UWG)
        self.dlg.pushButtonSave.clicked.connect(self.savefile)
        self.dlg.comboBoxVector.currentIndexChanged.connect(self.layer_changed)
        self.dlg.comboBoxField.currentIndexChanged.connect(self.attribute_changed)
        self.dlg.helpButton.clicked.connect(self.help)

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass
        else:
            self.dlg.__init__()

    def layer_changed(self):
            try:
                vector_cbox = self.dlg.comboBoxVector
                att_list = list(vector_cbox.currentLayer().attributeAliases())
                self.dlg.comboBoxField.clear()
                self.dlg.comboBoxField.addItems(att_list)
                self.dlg.comboBoxField.setCurrentIndex(0)

            except:
                pass

    def attribute_changed(self):
        
        layer = self.dlg.comboBoxVector.currentLayer()

        try:
            att_column = self.dlg.comboBoxField.currentText()
            att_list =[]

            for fieldName in layer.fields():
                att_list.append(fieldName.name())
            att_index = att_list.index(att_column)
   
            unique_values = list(layer.uniqueValues(att_index))
            # unique_values = ([str(x) for x in unique_values])
            print(unique_values)
            for i in range(0,21):
                # Oc == Old Class
                Oc = eval('self.dlg.lineEdit_' + str(i))
                Oc.clear()
                Oc.setDisabled(True)
                # Nc == New Class
                Nc = eval('self.dlg.comboBoxNew_' + str(i))
                Nc.setCurrentIndex(-1)
                Nc.setDisabled(True)
                # Pr == Period
                Pr = eval('self.dlg.comboBoxpPeriod_' + str(i))
                Pr.setCurrentIndex(-1)
                Pr.setDisabled(True)
                
            # Add Items to left side Comboboxes and enable right side comboboxes 
            for i in range(len(unique_values)):
                Oc = eval('self.dlg.lineEdit_' + str(i))
                Oc.clear()
                Oc.setText(unique_values[i])
                # Oc.setCurrentIndex(i)
                Nc = eval('self.dlg.comboBoxNew_' + str(i))
                Nc.setEnabled(True)
                Nc.setCurrentIndex(0)
                Pr = eval('self.dlg.comboBoxpPeriod_' + str(i))
                Pr.setCurrentIndex(0)
                Pr.setEnabled(True)
        except:
            pass
    
    # def type_info(self):

    #     # Create dict or similar to fill this.
    #     self.dlg.textBrowser.clear()

    #     # uwg_type = self.dlg.comboBoxTypeInfo.currentText()
        
    #     # self.dlg.textBrowser.setText(
    #     #     'UWG Type: '+ uwg_type +
    #     #     '\n\nOrigin: ' 'something' +
    #     #     '\n\nDescription: ' + 'something') 

    #     ref = {} # Here you can show UWG building type info

    #     self.dlg.textBrowserTypes.clear()
    #     try:
    #         ID = ref[ref['authorYear'] ==  self.dlg.comboBoxRef.currentText()].index.item()
    #         self.dlg.textBrowserTypes.setText(
    #             '<b>Author: ' +'</b>' + str(ref.loc[ID, 'Author']) + '<br><br><b>' +
    #             'Year: ' + '</b> '+ str(ref.loc[ID, 'Publication Year']) + '<br><br><b>' +
    #             'Title: ' + '</b> ' +  str(ref.loc[ID, 'Title']) + '<br><br><b>' +
    #             'Journal: ' + '</b>' + str(ref.loc[ID, 'Journal']) + '<br><br><b>'
    #             )
    #     except:
    #         pass

    def savefile(self):
        self.outputfile = self.fileDialog.getSaveFileName(None, 'Save File As:', None, 'Shapefiles (*.shp)')
        self.dlg.textOutput.setText(self.outputfile[0])
    
    def stopper(self):
        a = 1
        return

    def help(self):
        url = "http://umep-docs.readthedocs.io/en/latest/pre-processor/Urban%20Heat%20Island%20UWG%20Reclassifier.html"
        webbrowser.open_new_tab(url)

    def reclassify_to_UWG(self):
        if len(self.dlg.textOutput.text()) < 1:
            QMessageBox.critical(self.dlg, "Error", "No Output Folder selected")
            return

        att_column =  self.dlg.comboBoxField.currentText()
        vlayer = self.dlg.comboBoxVector.currentLayer()

        att_list = []
        for fieldName in vlayer.fields():
            att_list.append(fieldName.name())

        att_index = att_list.index(att_column)
        
        unique_values = list(vlayer.uniqueValues(att_index))
        
        dict_reclass = {}
        dict_period = {}
        for i in range(len(unique_values)):
            if i >20:
                break
            Oc = eval('self.dlg.lineEdit_' + str(i))
            oldField = Oc.text()
            Nc = eval('self.dlg.comboBoxNew_' + str(i))          
            dict_reclass[oldField] = str(Nc.currentText())
            Pr = eval('self.dlg.comboBoxpPeriod_' + str(i))      
            dict_period[oldField] = Pr.currentText()

        # # Add new field # TODO perhaps make it able for user to select field name
        # # fieldname = dlg.textEditFilename.text() or similar
        vlayer.dataProvider().addAttributes([QgsField('UWGType',QVariant.String)])
        vlayer.dataProvider().addAttributes([QgsField('UWGTime',QVariant.String)])
        vlayer.updateFields()

        typeIndex = vlayer.fields().indexFromName('UWGType') #The field needs to be created in advance
        attrmapType = {} #dictionary of feature id: {field index: new value}
        for f in vlayer.getFeatures():
            if f[att_column] in dict_reclass:
                attrmapType[f.id()] = {typeIndex:dict_reclass[f[att_column]]}

        vlayer.dataProvider().changeAttributeValues(attrmapType)
        vlayer.updateFields()

        timeIndex = vlayer.fields().indexFromName('UWGTime') #The field needs to be created in advance
        attrmapPeriod = {} #dictionary of feature id: {field index: new value}
        for f in vlayer.getFeatures():
            if f[att_column] in dict_period:
                attrmapPeriod[f.id()] = {timeIndex:dict_period[f[att_column]]}

        vlayer.dataProvider().changeAttributeValues(attrmapPeriod)
        vlayer.updateFields()

        # Write new Shapefile

        QgsVectorFileWriter.writeAsVectorFormat(vlayer, self.dlg.textOutput.text(), "UTF-8", vlayer.crs(), "ESRI Shapefile")

        # Remove created fields from original shapefile
        att_list = []
        for fieldName in vlayer.fields():
            att_list.append(fieldName.name())

        UWGType = att_list.index('UWGType')
        UWGTime = att_list.index('UWGTime')
        vlayer.dataProvider().deleteAttributes([UWGType, UWGTime])
        vlayer.updateFields()

        # Add newly created shapefile to Project
        new_vlayer = QgsVectorLayer(self.outputfile[0], Path(self.outputfile[0]).name[:-4])
        QgsProject.instance().addMapLayer(new_vlayer)

        QMessageBox.information(None, 'Process Complete', 'Your reclassified shapefile has been added to project. Proceed to UWG Preprare')
        self.dlg.textOutput.clear()
        
    def reset_plugin(self):
        self.dlg.comboBoxVector.setCurrentIndex(-1)
        self.dlg.comboBoxField.setCurrentIndex(-1)

        for i in range(0,21):
                    Oc = eval('self.dlg.lineEdit_' + str(i))
                    Oc.clear()
                    Oc.setDisabled(True)
                    Nc = eval('self.dlg.comboBoxNew_' + str(i))
                    Nc.setCurrentIndex(-1)
                    Nc.setDisabled(True)
                    Pr = eval('self.dlg.comboBoxpPeriod_' + str(i))
                    Pr.setCurrentIndex(-1)
                    Pr.setDisabled(True)
        vlayer = QgsVectorLayer(self.dlg.textOutput.text(), Path(self.outputfile[0]).name[:-4])
        QgsProject.instance().addMapLayer(vlayer)
        self.dlg.textOutput.clear()

    def closeEvent(self, event):
        self.reset_form()
        self.resetPlugin()
