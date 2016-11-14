# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TreeGenerator
                                 A QGIS plugin
 This plugin generates a vegetation canopy DSM and Trunk zone DSM from point data
                              -------------------
        begin                : 2016-10-25
        git sha              : $Format:%H$
        copyright            : (C) 2016 by Fredrik Lindberg
        email                : fredrikl@gvc.gu.se
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
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication
from PyQt4.QtGui import QAction, QIcon, QMessageBox, QFileDialog
from qgis.core import *
from ..Utilities.qgiscombomanager import *
import webbrowser
import os
from osgeo import gdal
import numpy as np
import makevegdems
from osgeo.gdalconst import *

# Import the code for the dialog
from tree_generator_dialog import TreeGeneratorDialog
import os.path


class TreeGenerator:
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
            'TreeGenerator_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)

        # Create the dialog (after translation) and keep reference
        self.dlg = TreeGeneratorDialog()
        self.dlg.runButton.clicked.connect(self.start_progress)
        self.dlg.pushButtonSave.clicked.connect(self.folder_path)
        self.dlg.helpButton.clicked.connect(self.help)

        self.fileDialog = QFileDialog()
        self.fileDialog.setFileMode(4)
        self.fileDialog.setAcceptMode(1)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Tree Generator')
        # TODO: We are going to let the user set this up in a future iteration
        # self.toolbar = self.iface.addToolBar(u'TreeGenerator')
        # self.toolbar.setObjectName(u'TreeGenerator')

        self.layerComboManagerPoint = VectorLayerCombo(self.dlg.comboBox_pointlayer)
        fieldgen = VectorLayerCombo(self.dlg.comboBox_pointlayer, initLayer="", options={"geomType": QGis.Point})
        self.layerComboManagerTreeTypeField = FieldCombo(self.dlg.comboBox_ttype, fieldgen, initField="")
        self.layerComboManagerTotalHeightField = FieldCombo(self.dlg.comboBox_totalheight, fieldgen, initField="")
        self.layerComboManagerTrunkHeightField = FieldCombo(self.dlg.comboBox_trunkheight, fieldgen, initField="")
        self.layerComboManagerDiameterField = FieldCombo(self.dlg.comboBox_diameter, fieldgen, initField="")

        self.layerComboManagerDSM = RasterLayerCombo(self.dlg.comboBox_DSM)
        RasterLayerCombo(self.dlg.comboBox_DSM, initLayer="")
        self.layerComboManagerDEM = RasterLayerCombo(self.dlg.comboBox_DEM)
        RasterLayerCombo(self.dlg.comboBox_DEM, initLayer="")
        self.layerComboManagerBuild = RasterLayerCombo(self.dlg.comboBox_Build)
        RasterLayerCombo(self.dlg.comboBox_Build, initLayer="")
        self.layerComboManagerCDSM = RasterLayerCombo(self.dlg.comboBox_CDSM)
        RasterLayerCombo(self.dlg.comboBox_CDSM, initLayer="")
        self.layerComboManagerTDSM = RasterLayerCombo(self.dlg.comboBox_TDSM)
        RasterLayerCombo(self.dlg.comboBox_TDSM, initLayer="")

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
        return QCoreApplication.translate('TreeGenerator', message)


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

        # Create the dialog (after translation) and keep reference
        self.dlg = TreeGeneratorDialog()

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/TreeGenerator/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u''),
            callback=self.run,
            parent=self.iface.mainWindow())


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Tree Generator'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        self.dlg.exec_()

        gdal.UseExceptions()
        gdal.AllRegister()

    def folder_path(self):
        self.fileDialog.open()
        result = self.fileDialog.exec_()
        if result == 1:
            self.folderPath = self.fileDialog.selectedFiles()
            self.dlg.textOutput.setText(self.folderPath[0])

    def start_progress(self):
        self.steps = 0
        point = self.layerComboManagerPoint.getLayer()
        if point is None:
            QMessageBox.critical(self.dlg, "Error", "No valid Point layer is selected")
            return

        if self.dlg.checkBoxOnlyBuilding.isChecked():  # Only building heights
            build = self.layerComboManagerBuild.getLayer()
            dsm = None
            dem = None
            if build is None:
                QMessageBox.critical(self.dlg, "Error", "No valid building raster layer is selected")
                return

            provider = build.dataProvider()
            filePath_build = str(provider.dataSourceUri())
            dataset = gdal.Open(filePath_build)
            build_array = dataset.ReadAsArray().astype(np.float)

        else:  # Both building ground heights
            dsm = self.layerComboManagerDSM.getLayer()
            dem = self.layerComboManagerDEM.getLayer()
            build = None
            if dsm is None:
                QMessageBox.critical(self.dlg, "Error", "No valid ground and building DSM raster layer is selected")
                return
            if dem is None:
                QMessageBox.critical(self.dlg, "Error", "No valid ground DEM raster layer is selected")
                return

            provider = dsm.dataProvider()
            filePath_dsm = str(provider.dataSourceUri())
            provider = dem.dataProvider()
            filePath_dem = str(provider.dataSourceUri())

            dataset = gdal.Open(filePath_dsm)
            dsm_array = dataset.ReadAsArray().astype(np.float)
            dataset2 = gdal.Open(filePath_dem)
            dem_array = dataset2.ReadAsArray().astype(np.float)

            if not (dsm_array.shape[0] == dem_array.shape[0]) & (dsm_array.shape[1] == dem_array.shape[1]):
                QMessageBox.critical(self.dlg, "Error", "All grids must be of same pixel resolution")
                return

            build_array = dsm_array - dem_array
            build_array[build_array < 2.] = 1.
            build_array[build_array >= 2.] = 0.

        sizey = build_array.shape[0]
        sizex = build_array.shape[1]

        if self.dlg.checkBoxMergeCDSM.isChecked():  # vegetation cdsm
            cdsm = self.layerComboManagerCDSM.getLayer()
            if cdsm is None:
                QMessageBox.critical(self.dlg, "Error", "No valid vegetation CDSM raster layer is selected")
                return

            provider = cdsm.dataProvider()
            filePath_cdsm = str(provider.dataSourceUri())

            dataset = gdal.Open(filePath_cdsm)
            cdsm_array = dataset.ReadAsArray().astype(np.float)
            tdsm = self.layerComboManagerCDSM.getLayer()
            if tdsm is None:
                QMessageBox.critical(self.dlg, "Error", "No valid vegetation TDSM raster layer is selected")
                return

            provider = tdsm.dataProvider()
            filePath_tdsm = str(provider.dataSourceUri())

            dataset = gdal.Open(filePath_tdsm)
            tdsm_array = dataset.ReadAsArray().astype(np.float)

        else:
            cdsm_array = np.zeros((sizey, sizex))
            tdsm_array = np.zeros((sizey, sizex))

        geotransform = dataset.GetGeoTransform()
        scale = 1 / geotransform[1]
        # nd = dataset.GetRasterBand(1).GetNoDataValue()
        # dem_array = np.zeros((sizex, sizey))

        # Get attributes
        vlayer = QgsVectorLayer(point.source(), "point", "ogr")
        # prov = vlayer.dataProvider()
        # fields = prov.fields()

        ttype_field = self.layerComboManagerTreeTypeField.getFieldName()
        trunk_field = self.layerComboManagerTrunkHeightField.getFieldName()
        tot_field = self.layerComboManagerTotalHeightField.getFieldName()
        dia_field = self.layerComboManagerDiameterField.getFieldName()

        idx_ttype = vlayer.fieldNameIndex(ttype_field)
        idx_trunk = vlayer.fieldNameIndex(trunk_field)
        idx_tot = vlayer.fieldNameIndex(tot_field)
        idx_dia = vlayer.fieldNameIndex(dia_field)

        if self.folderPath == 'None':
            QMessageBox.critical(self.dlg, "Error", "Select a valid output folder")
            return

        numfeat = vlayer.featureCount()
        width = dataset.RasterXSize
        height = dataset.RasterYSize
        minx = geotransform[0]
        miny = geotransform[3] + width * geotransform[4] + height * geotransform[5]
        rows = build_array.shape[0]
        cols = build_array.shape[1]

        self.dlg.progressBar.setRange(0, numfeat)
        index = 0
        # Main loop
        for f in vlayer.getFeatures():  # looping through each grid polygon

            # self.dlg.progressBar.setValue(0)
            index = index + 1
            self.dlg.progressBar.setValue(index)

            attributes = f.attributes()
            geometry = f.geometry()
            feature = QgsFeature()
            feature.setAttributes(attributes)
            feature.setGeometry(geometry)

            y = f.geometry().centroid().asPoint().y()
            x = f.geometry().centroid().asPoint().x()
            ttype = f.attributes()[idx_ttype]
            trunk = f.attributes()[idx_trunk]
            height = f.attributes()[idx_tot]
            dia = f.attributes()[idx_dia]
            cola = np.round(x - minx)
            rowa = np.round(miny + rows - y)

            # self.iface.messageBar().pushMessage("dia=", str(dia))
            # self.iface.messageBar().pushMessage("scale=", str(scale))
            # QMessageBox.information(None, "dia=", str(dia))
            # QMessageBox.critical(None, "x=", str(cdsm_array.shape[1]))
            # QMessageBox.critical(None, "y=", str(cdsm_array.shape[0]))

            cdsm_array, tdsm_array = makevegdems.vegunitsgeneration(build_array, cdsm_array, tdsm_array, ttype, height,
                                                                    trunk, dia, rowa, cola, sizex, sizey, scale)


        # self.saveraster(dataset, self.folderPath[0] + '/build.tif', build_array)
        self.saveraster(dataset, self.folderPath[0] + '/cdsm.tif', cdsm_array)
        self.saveraster(dataset, self.folderPath[0] + '/tdsm.tif', tdsm_array)

        QMessageBox.information(self.dlg, "TreeGenerator", "Vegetation DSMs succesfully generated")

    def help(self):
        # url = "file://" + self.plugin_dir + "/help/Index.html"
        url = "http://www.urban-climate.net/umep/UMEP_Manual#Pre-Processor:_Tree_Generator"
        webbrowser.open_new_tab(url)

    def saveraster(self, gdal_data, filename, raster):
        rows = gdal_data.RasterYSize
        cols = gdal_data.RasterXSize

        outDs = gdal.GetDriverByName("GTiff").Create(filename, cols, rows, int(1), GDT_Float32)
        outBand = outDs.GetRasterBand(1)

        # write the data
        outBand.WriteArray(raster, 0, 0)
        # flush data to disk, set the NoData value and calculate stats
        outBand.FlushCache()
        outBand.SetNoDataValue(-9999)

        # georeference the image and set the projection
        outDs.SetGeoTransform(gdal_data.GetGeoTransform())
        outDs.SetProjection(gdal_data.GetProjection())
