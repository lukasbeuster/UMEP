# -*- coding: utf-8 -*-
"""
/***************************************************************************
 VisualMain
                                 A QGIS plugin
 Visualisation of a 3D model to analyse Solar Energy and Photovoltaic Yield.

 major revision:
                              -------------------
        begin                : 2017-02-08
        by                   : Michael Revesz
        email                : revesz.michael@gmail.com

 original:
                              -------------------
        begin                : 2014-03-20
        copyright            : (C) 2014 by Niklas Krave
        email                : niklaskrave@gmail.com
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
# Import the PyQt and QGIS libraries
from qgis.core import QgsRasterLayer, QgsProject, QgsVectorLayer, QgsFeature, QgsRectangle, QgsGeometry, QgsMessageLog, Qgis, QgsPointXY
from qgis.utils import *
from qgis.gui import *
from qgis.PyQt import QtWidgets
from qgis.PyQt.QtCore import QSettings, QTranslator, qVersion, QThread, QCoreApplication
from qgis.PyQt.QtGui import QIcon, QPixmap, QScreen
from qgis.PyQt.QtWidgets import QAction, QFileDialog, QMessageBox

# Initialize Qt resources from file resources.py
# import resources

import sys
import os.path
from osgeo import gdal
import subprocess
import numpy as np
import webbrowser
import matplotlib
# Make sure that we are using QT5
matplotlib.use('Qt5Agg')
from matplotlib.figure import Figure
from matplotlib import colorbar, colors
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

# Import the code for the GUI dialog
from .visualizer_dialog import VisualizerDialog
from .tools.GLWidget import VisWidget
from .tools.areaTool import AreaTool
from .tools.lineEditDragDrop import LineEditDragFile
from .wallworker import wallWorker

# from .rectangleAreaTool import RectangleAreaTool


def get_dsm_corners(filepath):
    """Used to load a dsm for Area selection while testing. Calculated 2 diagonal corners of area rectangle"""
    gdal_dsm = gdal.Open(filepath)
    ncols = gdal_dsm.RasterXSize
    nrows = gdal_dsm.RasterYSize
    geotransform = gdal_dsm.GetGeoTransform()
    # tl= top left, br= bottom right
    xtl = geotransform[0]
    ytl = geotransform[3]
    xbr = geotransform[0] + ncols * geotransform[1] + nrows * geotransform[2]
    ybr = geotransform[3] + ncols * geotransform[4] + nrows * geotransform[5]

    return xtl, ytl, xbr, ybr


def valid_float(value):
    """ Returns True if value can be converted to float,
        otherwise returns False.
    """
    try:
        float(value)
    except ValueError:
        return False
    else:
        return True


class Visual:
    # Runs when QGis starts up and the plugin is set to be active
    def __init__(self, iface, screen=None):
        """ Initialization
        :param iface: Reference to QGIS interface, is None if run as __main__
        """

        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)

        if self.iface is not None:
            # initialize locale
            locale = QSettings().value("locale/userLocale")[0:2]
            localePath = os.path.join(self.plugin_dir, 'i18n', 'sun_{}.qm'.format(locale))

            if os.path.exists(localePath):
                self.translator = QTranslator()
                self.translator.load(localePath)

                if qVersion() > '4.3.3':
                    QCoreApplication.installTranslator(self.translator)

            # variables for additional layers
            self.layer = None
            self.dsmlayer = None  # dsm of selected area (used for testing)
            self.polyLayer = None

            # Create a reference to the map canvas
            self.canvas = self.iface.mapCanvas()
            # Create tools
            self.areaTool = AreaTool(self.canvas)
            self.areaTool.areaComplete.connect(self.display_area)

            # other variables used only with QGIS:
            self.initialize = None
            self.toolBar = None

        # Create the dialog (after translation) and keep reference
        self.visDlg = VisualizerDialog()

        # For adopting widget size to screen resolution:
        try:
            screensize = screen.size()
        except AttributeError:
            screenw, screenh = 900, 800
        else:
            screenw, screenh = screensize.width(), screensize.height()
        self.screenw = screenw // 4    # screen-width
        self.screenh = screenh // 2    # screen-height

        self.windowtitle = "SEBE(pv) Visualizer"   # Main title to be shown in window title
        self.GLsize = (0, 0)   # width, height of GL drawinf area to be shown in window title
        self.graphtitle = ""   # wall file name to be shown in window title

        self.base_path_str = None       # string of the path of data
        self.point1 = None
        self.point2 = None
        self.gl_widget = None
        self.energy_array = None
        self.dsm_array = None

        self.xulcorner = None   # corners of selected dsm area
        self.yulcorner = None
        self.cellsizex = None
        self.cellsizey = None
        self.xulcorner_sel = None
        self.yulcorner_sel = None

        # default file names:
        self.roofground_default = 'Energyyearroof.tif'
        self.veg_default = 'Vegetationdata.txt'
        self.wall_default = 'Energyyearwall.txt'
        self.height_default = 'dsm.tif'

        self.roofground_file = None
        self.veg_file = None
        self.wall_file = None
        self.height_file = None

        self.showpv = False          # if True, prefix wall and roof files with 'PV'

        self.thread = None
        self.wallworker = None
        self.steps = 0

        self.visDlg.ButtonSelect.clicked.connect(self.area)
        self.visDlg.ButtonDirectory.clicked.connect(self.data_directory)
        self.visDlg.ButtonVisualize.clicked.connect(self.visualize)
        self.visDlg.ButtonHelp.clicked.connect(self.help)
        self.visDlg.ButtonSave.clicked.connect(self.savescreen)
        self.visDlg.ButtonSave.setEnabled(0)
        self.visDlg.checkBoxPV.stateChanged.connect(self.use_pv_changed)
        self.visDlg.checkBoxPV.setEnabled(0)
        self.visDlg.ButtonClose.clicked.connect(self.cleanup)

        self.fileDialog = None      # for file dialog to choose data folder

        LineEditDragFile(self.visDlg.textOutput)
        self.visDlg.textOutput.textChanged.connect(self.process_paths)
        # hide sliders until visualized:
        self.visDlg.frameSetView.hide()
        self.autorange = True

        # Set QDialog size:
        self.visDlg.resize(self.screenw, self.screenh)

        gdal.UseExceptions()  # make gdal throw python exceptions

    def initGui(self):
        """ Create toolbar within UMEP plugin for QGIS
        :return:
        """
        self.toolBar = self.iface.addToolBar("Sun Toolbar")

        # Action for initializing the plugin, will add shape-files and OLlayer to the QGis-project
        self.initialize = QAction(
            QIcon(":/plugins/sun/initicon.png"),
            u"Initialize plugin environment", self.iface.mainWindow())

        self.initialize.triggered.connect(self.run)

        self.toolBar.addAction(self.initialize)

    def unload(self):
        """ Runs when the plugin is deleted, remove it from QGIS toolbar.
        :return:
        """
        del self.toolBar

    def run(self):
        """ Initialisation method
        :return:
        """
        self.visDlg.open()
        self.visDlg.exec_()

    def help(self):
        url = "http://bitbucket.org/pvoptiray/umep-3d/wiki/Manual#!sebepv-visualizer"
        webbrowser.open_new_tab(url)

    def area(self):
        """ Select an area of the scene for visualisation
        :return:
        """
        xtl, ytl, xbr, ybr = get_dsm_corners(self.base_path_str + '/' + self.height_file)
        self.point1 = QgsPointXY(xtl, ytl)
        self.point2 = QgsPointXY(xbr, ybr)

        QMessageBox.warning(self.visDlg, "Full extent will be selected", "This functionality is currently not active. "
                                "Full extent will used for visualisation. For large model domains, this will make the plugin low in performance.")

        self.visDlg.ButtonVisualize.setEnabled(1)
        
        #TODO: Make user define area to visualise
        # if self.iface is None:
        #     # changed for testing:
        #     xtl, ytl, xbr, ybr = get_dsm_corners(self.base_path_str + '/' + self.height_file)
        #     self.point1 = QgsPointXY(xtl, ytl)
        #     self.point2 = QgsPointXY(xbr, ybr)

        #     self.visDlg.ButtonVisualize.setEnabled(1)
        # else:
        #     # self.iface.mapCanvas().setMapTool(self.rectangleAreaTool)
        #     # AreaTool(self.canvas)
        #     self.canvas.setMapTool(self.AreaTool)

    def data_directory(self):
        """ Select directory with data and test if valid. """
        self.fileDialog = QFileDialog()
        self.fileDialog.setFileMode(2)
        self.fileDialog.setAcceptMode(0)
        self.fileDialog.open()

        result = self.fileDialog.exec_()
        if result == 1:
            data_path = self.fileDialog.selectedFiles()
            self.base_path_str = str(data_path[0])

        self.visDlg.ButtonVisualize.setEnabled(False)  # see, if needed here also for QGIS plugin!!
        self.visDlg.textOutput.setText(self.base_path_str)

    def process_paths(self):
        """ Process the directory path or file-paths and check if valid. """

        # reset data paths:
        self.base_path_str = None
        self.roofground_file = None
        self.veg_file = None
        self.wall_file = None
        self.height_file = None

        if self.iface is not None:
            # delete open layers from QGIS:
            self.remove_layers()

        paths = self.visDlg.textOutput.text()
        if ";" in paths:
            # files given:
            self.visDlg.checkBoxPV.setEnabled(False)

            pathslist = paths.split(";")
            pathendindex = pathslist[0].rfind("/")+1
            self.base_path_str = pathslist[0][0:pathendindex]
            for i in pathslist:
                if "roof" in i:
                    self.roofground_file = i[pathendindex:]
                elif "wall" in i:
                    self.wall_file = i[pathendindex:]
                elif "dsm" in i:
                    self.height_file = i[pathendindex:]
                elif "veg" in i:
                    self.veg_file = i[pathendindex:]
            if self.height_file is None:
                self.height_file = self.height_default

            # check if data is PV yield or irradiation:
            if ("PV" in self.roofground_file) or ("PV" in self.wall_file):
                self.showpv = True
            else:
                self.showpv = False
        else:
            # directory given:
            self.base_path_str = paths + "/"
            self.height_file = self.height_default

            fileslist = os.listdir(self.base_path_str)
            if self.roofground_default in fileslist and 'PV'+self.roofground_default in fileslist:
                self.visDlg.checkBoxPV.setEnabled(True)

                self.roofground_file = self.roofground_default
                self.veg_file = self.veg_default
                self.wall_file = self.wall_default
                self.showpv = False

                QMessageBox.warning(None, "Warning",
                                    "Check the checkbox 'Show PV'! \n Choose Irradiance or Photovoltaic."
                                    )
            elif self.roofground_default in fileslist:
                self.visDlg.checkBoxPV.setEnabled(False)
                self.showpv = False

                self.roofground_file = self.roofground_default
                self.veg_file = self.veg_default
                self.wall_file = self.wall_default
            elif 'PV'+self.roofground_default in fileslist:
                self.visDlg.checkBoxPV.setEnabled(False)
                self.showpv = True

                self.roofground_file = "PV" + self.roofground_default
                self.veg_file = "PV" + self.veg_default
                self.wall_file = "PV" + self.wall_default

        if self.check_data_exist():
            if self.iface is not None:
                # Load Energyyearroof as layer to QGIS:
                self.layer = QgsRasterLayer(self.base_path_str + self.height_file, "loaded DSM")
                loadedlayer = self.iface.addRasterLayer(self.base_path_str + self.height_file)
                #loadedlayer = QgsMapLayerRegistry.instance().addMapLayer(self.layer)
                loadedlayer.triggerRepaint()

            self.visDlg.ButtonSelect.setEnabled(True)  # enables area selection
        else:
            self.visDlg.ButtonSelect.setEnabled(False)

    def use_pv_changed(self):
        if self.visDlg.checkBoxPV.isChecked():
            self.showpv = True
            self.roofground_file = "PV" + self.roofground_default
            self.veg_file = "PV" + self.veg_default
            self.wall_file = "PV" + self.wall_default
        else:
            self.showpv = False
            self.roofground_file = self.roofground_default
            self.veg_file = self.veg_default
            self.wall_file = self.wall_default

    def check_data_exist(self):

        err = ""
        #print(err)
        # check dsm file:
        try:
            layer = gdal.Open(str(self.base_path_str + self.height_file))
        except (RuntimeError, TypeError) as err:
            layer = None
        if layer is None:
            QMessageBox.critical(None, "Error",
                                 "Could not find valid ground .tif file in directory!\n" + str(err)
                                 )
            return 0
        # check energy-roof file:
        try:
            layer = gdal.Open(str(self.base_path_str + self.roofground_file))
        except (RuntimeError, TypeError) as err:
            layer = None
        if layer is None:
            QMessageBox.critical(None, "Error",
                                 ("Could not find valid energy on roof/ground .tif file in directory!\n" +
                                  str(err))
                                 )
            return 0
        # check energy-wall file:
        try:
            layer = open(str(self.base_path_str + self.wall_file), 'r')
        except (RuntimeError, TypeError) as err:
            layer = None
        if layer is None:
            QMessageBox.critical(None, "Error", "Could not find valid wall .txt file in directory!\n" + str(err))
            return 0
        return 1

    def display_area(self, point1, point2):
        """ Adds the selected study area as poly layer to QGIS
        (Not used if run as __main__)

        :param point1: 1st QgsPoint of selected area
        :param point2: 2nd QgsPoint of selected area
        :return:
        """
        self.point1 = point1
        self.point2 = point2

        self.remove_layers(all_layers=False)
        srs = self.canvas.mapSettings().destinationCrs()
        crs = str(srs.authid())
        uri = "Polygon?field=id:integer&index=yes&crs=" + crs
        self.polyLayer = QgsVectorLayer(uri, "Study area", "memory")
        provider = self.polyLayer.dataProvider()

        fc = int(provider.featureCount())
        featurepoly = QgsFeature()

        rect = QgsRectangle(point1, point2)
        featurepoly.setGeometry(QgsGeometry.fromRect(rect))
        featurepoly.setAttributes([fc])
        self.polyLayer.startEditing()
        self.polyLayer.addFeature(featurepoly, True)
        self.polyLayer.commitChanges()
        self.iface.addVectorLayer(self.polyLayer)
        #QgsMapLayerRegistry.instance().addMapLayer(self.polyLayer)

        self.polyLayer.setLayerTransparency(42)

        self.polyLayer.triggerRepaint()
        self.visDlg.ButtonVisualize.setEnabled(1)

    def visualize(self):
        """Load data files, prepare area clipping, initiate visualisation"""

        self.steps = 0
        gdal.UseExceptions()
        self.check_data_exist()     # in case the checkbox got changed in the meanwhile

        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        if self.point1.x() > self.point2.x():
            minx = self.point2.x()
            maxx = self.point1.x()
        else:
            minx = self.point1.x()
            maxx = self.point2.x()

        if self.point1.y() > self.point2.y():
            miny = self.point2.y()
            maxy = self.point1.y()
        else:
            miny = self.point1.y()
            maxy = self.point2.y()

        # # Help with gdal:
        # ds = gdal.Open('path/to/file')
        #
        # width = ds.RasterXSize
        # height = ds.RasterYSize
        #
        # gt = ds.GetGeoTransform()
        # minx = gt[0]
        # miny = gt[3] + width * gt[4] + height * gt[5]  # from
        # http: // gdal.org / gdal_datamodel.html
        # maxx = gt[0] + width * gt[1] + height * gt[2]  # from
        # http: // gdal.org / gdal_datamodel.html
        # maxy = gt[3]
        #
        # topLeftX = geoinformation[0]
        # topLeftY = geoinformation[3]
        #####

        # load data and clip area:
        # roofground:
        surface_full = gdal.Open(self.base_path_str + self.roofground_file)

        geotransform = surface_full.GetGeoTransform()
        self.xulcorner = geotransform[0]
        self.yulcorner = geotransform[3]
        self.cellsizex = geotransform[1]
        self.cellsizey = geotransform[5]

        ulcorner = (geotransform[0], geotransform[3])  # x, y for upper left corner
        cellsize = (geotransform[1], geotransform[5])   # gridsize in x, y direction

        gdalclip_build = 'gdal_translate -a_nodata -9999 -projwin ' + str(minx) + ' ' + str(maxy) \
                         + ' ' + str(maxx) + ' ' + str(miny) + \
                         ' -of GTiff ' + self.base_path_str + self.roofground_file + ' ' \
                         + self.plugin_dir + '/data/temp.tif'

        subprocess.call(gdalclip_build, startupinfo=si)

        # ground energy data for selected area:
        dataset = gdal.Open(self.plugin_dir + '/data/temp.tif')
        self.energy_array = dataset.ReadAsArray().astype(float)

        sizex = self.energy_array.shape[1]
        sizey = self.energy_array.shape[0]

        # dsm:
        gdalclipasc_build = 'gdal_translate -a_nodata -9999 -projwin ' + \
                            str(minx) + ' ' + str(maxy) + ' ' + str(maxx) + ' ' + str(miny) + \
                            ' -of GTiff ' + self.base_path_str + self.height_file + ' ' + \
                            self.plugin_dir + '/data/temp_asc.tif'

        subprocess.call(gdalclipasc_build, startupinfo=si)

        # dsm data for selected area:
        dataset = gdal.Open(self.plugin_dir + '/data/temp_asc.tif')

        select_geotransform = dataset.GetGeoTransform()
        self.xulcorner_sel = select_geotransform[0]
        self.yulcorner_sel = select_geotransform[3]

        select_ulcorner = (select_geotransform[0], select_geotransform[3])   # x, y for upper left corner
        select_size = (sizex, sizey)   # size of selected array in x, y direction

        self.dsm_array = dataset.ReadAsArray().astype(float)
        np.place(self.dsm_array, self.dsm_array == -9999., np.nan)

        # if self.iface is not None:
        #     # Load dsm of selected area as layer to QGIS:
        #     self.dsmlayer = QgsRasterLayer(self.plugin_dir + '/data/temp_asc.tif', "selected DSM")
            
        #     #selectedlayer = QgsMapLayerRegistry.instance().addMapLayer(self.dsmlayer)
        #     selectedlayer = self.iface.addRasterLayer(self.plugin_dir + '/data/temp_asc.tif')
        #     selectedlayer.triggerRepaint()

        # movie = QMovie(self.plugin_dir + '/loader.gif')
        # self.visDlg.label.setMovie(movie)
        # self.visDlg.label.show()
        # movie.start()

        self.start_wallworker(ulcorner, cellsize, select_size, select_ulcorner)

    def start_wallworker(self, ulcorner, cellsize, select_size, select_ulcorner):
        # create a new worker instance
        worker = wallWorker(ulcorner, cellsize, select_size, select_ulcorner, self.base_path_str, self.wall_file)

        self.visDlg.ButtonVisualize.setText('Cancel')
        self.visDlg.ButtonVisualize.clicked.disconnect()
        self.visDlg.ButtonVisualize.clicked.connect(self.kill_worker)
        self.visDlg.ButtonClose.setEnabled(False)

        # start the worker in a new thread
        thread = QThread(self.visDlg)
        worker.moveToThread(thread)

        worker.finished.connect(self.worker_finished)
        worker.error.connect(self.worker_error)
        # worker.progress.connect(self.progress_update)
        thread.started.connect(worker.run)
        
        thread.start()
        self.thread = thread
        self.wallworker = worker

    def worker_error(self, e, exception_string):
        strerror = "Worker thread raised an exception: " + str(e)
        # print(strerror)
        QgsMessageLog.logMessage(strerror.format(exception_string), level=2)
        # QgsMessageLog.logMessage(strerror.format(exception_string), level=QgsMessageLog.CRITICAL)

    # def progress_update(self):
    #     pass

    def kill_worker(self):
        self.wallworker.kill()

    def worker_finished(self, ret):
        # clean up the wallworker and thread
        wall_array = ret
        self.wallworker.deleteLater()
        self.thread.quit()
        self.thread.wait()
        self.thread.deleteLater()

        if ret is not None:
            QgsMessageLog.logMessage('WALL_ARRAY length: ' + str(len(ret)), level=2)
            QgsMessageLog.logMessage('WALL_ARRAY: ' + str(ret), level=2)
            QgsMessageLog.logMessage('ASC_ARRAY: ' + str(self.dsm_array), level=2)

            renewWidget = True
            if self.gl_widget is not None:
                if np.array_equal(self.gl_widget.dsm_array, self.dsm_array):
                    # reuse same gl_widget settings for view!
                    renewWidget = False
                    self.gl_widget.reinitiate(self.energy_array, self.dsm_array, wall_array,
                                              self.cellsizex, self.cellsizey)
                else:
                    renewWidget = True
                    self.visDlg.layout.removeWidget(self.gl_widget)
            else:
                pass
            if renewWidget:
                # i.e. widget wasnt initiated at all, or should be renewed:
                self.gl_widget = VisWidget(self.energy_array, self.dsm_array, wall_array,
                                           self.cellsizex, self.cellsizey, self)
                self.visDlg.layout.addWidget(self.gl_widget, 0, 0)
            else:
                pass
            # add the colorbar to frame:
            self.redraw_colorbar()

        self.visDlg.ButtonVisualize.setText('Visualize')
        self.visDlg.ButtonVisualize.clicked.disconnect()
        self.visDlg.ButtonVisualize.clicked.connect(self.visualize)
        self.visDlg.ButtonClose.setEnabled(True)
        self.visDlg.ButtonClose.clicked.connect(self.visDlg.close)
        self.visDlg.ButtonSave.setEnabled(1)

        # Now show all text fields for setting the visualization:
        self.visDlg.frameSetView.show()

        # set initial values to lineEdits:
        self.visDlg.TextAzim.setText(str(self.gl_widget.get_zrot()))
        self.visDlg.TextZeni.setText(str(self.gl_widget.get_xrot()))
        self.visDlg.TextViewDist.setText(str(self.gl_widget.get_viewdist()))
        self.visDlg.TextShiftX.setText(str(self.gl_widget.get_xshift()))
        self.visDlg.TextShiftY.setText(str(self.gl_widget.get_yshift()))

        # signals to textEdit lines:
        self.visDlg.TextAzim.editingFinished.connect(self.txt_changed_azim)
        self.visDlg.TextZeni.editingFinished.connect(self.txt_changed_zeni)
        self.visDlg.TextViewDist.editingFinished.connect(self.txt_changed_zoom)
        self.visDlg.TextShiftX.editingFinished.connect(self.txt_changed_xshft)
        self.visDlg.TextShiftY.editingFinished.connect(self.txt_changed_yshft)

        self.visDlg.ButtonRange.setCheckable(True)
        self.visDlg.ButtonRange.setChecked(True)
        self.visDlg.ButtonRange.toggled.connect(self.printautorange)
        self.visDlg.textMinimum.editingFinished.connect(self.min_energy_changed)
        self.visDlg.textMaximum.editingFinished.connect(self.max_energy_changed)
        self.visDlg.label_14.hide()
        self.visDlg.label_15.hide()
        self.visDlg.textMinimum.hide()
        self.visDlg.textMaximum.hide()
        self.visDlg.ButtonRedraw.hide()
        self.visDlg.ButtonRedraw.clicked.connect(self.redrawGL)

        # update the main-window title, show which file is shown now:
        self.update_title_filename()

    def printautorange(self, value):
        self.autorange = value
        if self.autorange:
            self.visDlg.ButtonRange.setText('set Manual Range')
            self.visDlg.label_14.hide()
            self.visDlg.label_15.hide()
            self.visDlg.textMinimum.hide()
            self.visDlg.textMaximum.hide()
            self.visDlg.ButtonRedraw.hide()
            self.gl_widget.calc_minmax_energy()
            self.gl_widget.calc_energyrange()
            # redraw object with new colors:
            self.gl_widget.object = self.gl_widget.createObject()
            self.gl_widget.updateGL()
            self.redraw_colorbar()
        elif not self.autorange:
            self.visDlg.ButtonRange.setText('set Auto Range')
            self.visDlg.ButtonRedraw.show()
            self.visDlg.label_14.show()
            self.visDlg.label_15.show()
            self.visDlg.textMinimum.show()
            self.visDlg.textMaximum.show()
            self.visDlg.textMinimum.setText(str(self.gl_widget.get_min_energy()))
            self.visDlg.textMaximum.setText(str(self.gl_widget.get_max_energy()))

    def redrawGL(self):
        if (self.visDlg.textMaximum.text() == "invalid number") or (self.visDlg.textMinimum.text() == "invalid number"):
            pass
        else:
            self.gl_widget.calc_energyrange()
            self.gl_widget.object = self.gl_widget.createObject()
            self.gl_widget.updateGL()

            self.redraw_colorbar()

    def min_energy_changed(self):
        value = self.visDlg.textMinimum.text()
        if valid_float(value) and (value != self.gl_widget.get_min_energy()):
            self.gl_widget.set_min_energy(float(value))
        else:
            self.visDlg.textMinimum.setText("invalid number")

    def max_energy_changed(self):
        value = self.visDlg.textMaximum.text()
        if valid_float(value) and (value != self.gl_widget.get_max_energy()):
            self.gl_widget.set_max_energy(float(value))
        else:
            self.visDlg.textMaximum.setText("invalid number")

    def txt_update_azim(self, value):
        """ when azimuth value is changed in GL"""
        self.visDlg.TextAzim.setText(str(value))

    def txt_update_zeni(self, value):
        """ when zenith value is changed in GL"""
        self.visDlg.TextZeni.setText(str(value))

    def txt_update_zoom(self, value):
        """ when zoom value is changed in GL"""
        self.visDlg.TextViewDist.setText(str(value))

    def txt_update_xshf(self, value):
        """ when x-shift value is changed in GL"""
        self.visDlg.TextShiftX.setText(str(value))

    def txt_update_yshf(self, value):
        """ when y-shift value is changed in GL"""
        self.visDlg.TextShiftY.setText(str(value))

    def txt_changed_azim(self):
        value = self.visDlg.TextAzim.text()
        if valid_float(value) and (value != self.gl_widget.get_zrot()):
            self.gl_widget.set_zrot(int(value))
            self.gl_widget.updateGL()
        else:
            pass

    def txt_changed_zeni(self):
        value = self.visDlg.TextZeni.text()
        if valid_float(value) and (value != self.gl_widget.get_xrot()):
            self.gl_widget.set_xrot(int(value))
            self.gl_widget.updateGL()
        else:
            pass

    def txt_changed_zoom(self):
        value = self.visDlg.TextViewDist.text()
        if valid_float(value) and (value != self.gl_widget.get_viewdist()):
            self.gl_widget.set_viewdist(int(value))
            self.gl_widget.updateGL()
        else:
            pass

    def txt_changed_xshft(self):
        value = self.visDlg.TextShiftX.text()
        if valid_float(value) and (value != self.gl_widget.get_xshift()):
            self.gl_widget.set_xshift(int(value))
            self.gl_widget.updateGL()
        else:
            pass

    def txt_changed_yshft(self):
        value = self.visDlg.TextShiftY.text()
        if valid_float(value) and (value != self.gl_widget.get_yshift()):
            self.gl_widget.set_yshift(int(value))
            self.gl_widget.updateGL()
        else:
            pass

    def redraw_colorbar(self):
        # delete old colorbar:
        try:
            self.visDlg.layoutBar.removeWidget(self.colorbar)
            self.colorbar.deleteLater()
        except:
            pass
        # add new color bar:
        self.figure = Figure(figsize=(1, 10), facecolor='white')
        self.colorbar = FigureCanvas(self.figure)
        ax1 = self.figure.add_axes([0.05, 0.05, 0.15, 0.9])  # left bottom width height (fraction of figsize)
        norm = colors.Normalize(vmin=self.gl_widget.get_min_energy(), vmax=self.gl_widget.get_max_energy())
        cb1 = colorbar.ColorbarBase(ax1,
                                    cmap=self.gl_widget.cm,
                                    norm=norm,
                                    orientation='vertical',
                                    format='%.2e')
        if self.showpv:
            cb1.set_label('PV Yield [kWh/kWp]')
        else:
            cb1.set_label('Irradiation [kWh/m2]')
        self.visDlg.layoutBar.addWidget(self.colorbar, 0, 0)

    def getRelativeFrameGeometry(self, widget):
        g = widget.geometry()
        fg = widget.frameGeometry()
        return fg.translated(-g.left(), -g.top())

    def savescreen(self):
        filename = 'output.png'
        #####
        # for name, widget in self.visDlg:
        # pixmap = QPixmap.grabWidget(self.visDlg

        # pixmap = self.gl_widget.grab()
        # pixmap=self.visDlg.layoutContain.grab()
        # pixmap.save(self.base_path_str + "1b-sssss" + ".jpg")

        # rfg = self.getRelativeFrameGeometry(self.visDlg.layoutContain)
        # pix = QPixmap(self.visDlg.layoutContain.size())
        # self.visDlg.layoutContain.render(pix)
        # pix.save(self.base_path_str + "2-sssss" + ".jpg")

        #screen = QtWidgets.QApplication.primaryScreen()
        ##screenshot = screen.grabWindow(self.visDlg.winId())
        #screenshot = screen.grabWindow(self.visDlg.layoutContain.winId())
        #screenshot.save(self.base_path_str + "3-sssss" + ".tif")

        #pixmap = QScreen.grabWindow(self.visDlg.layoutContain[rfg.left(), rfg.top(), rfg.width(), rfg.height()])
        #print(rfg.left(), rfg.top(), rfg.width(), rfg.height())
        try:
            screen = QtWidgets.QApplication.primaryScreen()
            #screenshot = screen.grabWindow(self.visDlg.winId())
            screenshot = screen.grabWindow(self.visDlg.layoutContain.winId())
            screenshot.save(self.base_path_str + filename)
            # pixmap.save(self.base_path_str + filename, fileformat)
            QMessageBox.information(self.visDlg, "Information", "Image saved as: " + "\n" + self.base_path_str + filename)
        except TypeError:
            print("Screen not saved! TypeError. \ndirectory: %s \nfilename: %s" % (self.base_path_str, filename))

    def update_windowsize(self, width, height):
        """ Print new screen size of GLWidget to App-menu

        :param width: Width of screen size
        :param height: Height of screen size
        :return:
        """
        self.GLsize = (width, height)   # update GL-graph area size
        title = self.windowtitle + (" - w: %s h: %s - " % self.GLsize) + self.graphtitle
        self.visDlg.setWindowTitle(title)

    def update_title_filename(self):
        """
        Updates the window title to show open wall-file name.
        :return:
        """
        self.graphtitle = str(self.wall_file[:-4])   # update graph-title with file-name
        title = self.windowtitle + (" - w: %s h: %s - " % self.GLsize) + self.graphtitle
        self.visDlg.setWindowTitle(title)

    def remove_layers(self, all_layers=True):
        """ Remove open layers from QGIS.
        (Not used if run as __main__)
        :param all_layers: Boolean, True if all layers should be removed from QGIS
        :return:
        """

        if self.polyLayer is not None:
            self.polyLayer.startEditing()
            self.polyLayer.selectAll()
            self.polyLayer.deleteSelectedFeatures()
            self.polyLayer.commitChanges()
            #QgsMapLayerRegistry.instance().removeMapLayer(self.polyLayer.id())
            self.polyLayer = None
        # delete full dsm layer from QGIS:
        if (self.layer is not None) and all_layers:
            #QgsMapLayerRegistry.instance().removeMapLayer(self.layer)
            self.layer = None
        # delete selected dsm layer from QGIS:
        if self.dsmlayer is not None:
            #QgsMapLayerRegistry.instance().removeMapLayer(self.dsmlayer)
            self.dsmlayer = None

    def cleanup(self):
        """ Cleanup: Remove layers from QGIS and close widget.

        :return:
        """
        if self.iface is not None:
            # delete area-selection layer from QGIS:
            self.remove_layers()
        # close dialogue:
        self.visDlg.close()
        if self.iface is None:
            sys.exit(0)


# if __name__ == '__main__':
#     app = QtWidgets.QApplication(sys.argv)

#     visual = Visual(None, screen=app.primaryScreen())
#     visual.run()
#     app.exec_()
#     sys.exit(app.exec_())
