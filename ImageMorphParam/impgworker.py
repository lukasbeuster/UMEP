# -*- coding: utf-8 -*-
from PyQt4 import QtCore
from PyQt4.QtCore import QVariant
from PyQt4.QtGui import QMessageBox # QFileDialog, QAction, QIcon,
# from qgis.gui import *
from qgis.core import QgsVectorLayer, QgsVectorFileWriter, QgsFeature, QgsRasterLayer, QgsGeometry, QgsMessageLog
from qgis.core import *
import traceback
from ..Utilities.imageMorphometricParms_v1 import *
from ..Utilities import RoughnessCalcFunction as rg
# import Image
from scipy import *
import numpy as np
import linecache
# from ..Utilities.qgiscombomanager import *
from osgeo import gdal
import subprocess
# import os
# import PIL
# from paramWorker import ParamWorker
# from pydev import pydevd
import sys
import os

class Worker(QtCore.QObject):

    # Implementation av de signaler som traden skickar
    finished = QtCore.pyqtSignal(bool)
    error = QtCore.pyqtSignal(object)
    progress = QtCore.pyqtSignal()

    def __init__(self, dsm, dem, dsm_build, poly, poly_field, vlayer, prov, fields, idx, dir_poly, iface, plugin_dir,
                 folderPath, dlg, imid, radius, degree, rm):
        QtCore.QObject.__init__(self)
        # Boolean som berattar for traden ifall den har avbrutits
        self.killed = False
        # skapar referenser till all data som skickas in till traden, maste goras for att variablerna ska kunna nas
        # i run()-metoden och alla andra metoder klassen kan tankas ha.
        self.dsm = dsm
        self.dem = dem
        self.dsm_build = dsm_build
        self.poly = poly
        self.poly_field = poly_field
        self.vlayer = vlayer
        self.prov = prov
        self.fields = fields
        self.idx = idx
        self.dir_poly = dir_poly
        self.iface = iface
        self.plugin_dir = plugin_dir
        self.folderPath = folderPath
        self.dlg = dlg
        self.imid = imid
        self.radius = radius
        self.degree = degree
        self.rm = rm

        # Forsok till att skapa ytterligare tradar, anvands inte for tillfallet.
        self.paramthread = None
        self.paramworker = None

    def run(self):
        # index = 0
        arrmat = np.empty((1, 8))

        #Check OS and dep
        if sys.platform == 'darwin':
            gdalwarp_os_dep = '/Library/Frameworks/GDAL.framework/Versions/Current/Programs/gdalwarp'
        else:
            gdalwarp_os_dep = 'gdalwarp'

        ret = 0
        imp_point = 0

        # Allt arbete en trad ska utforas maste goras i en try-sats
        try:
            # j = 0
            # Loop som utfor det arbete som annars hade "hangt" anvandargranssnittet i Qgis
            pre = self.dlg.textOutput_prefix.text()
            for f in self.vlayer.getFeatures():  # looping through each grid polygon
                # Kollar sa att traden inte har avbrutits, ifall den har det sa slutar loopning.
                if self.killed is True:
                    break
                # pydevd.settrace('localhost', port=53100, stdoutToServer=True, stderrToServer=True) #used for debugging

                attributes = f.attributes()
                geometry = f.geometry()
                feature = QgsFeature()
                feature.setAttributes(attributes)
                feature.setGeometry(geometry)

                if self.imid == 1:  # use center point
                    r = self.radius
                    y = f.geometry().centroid().asPoint().y()
                    x = f.geometry().centroid().asPoint().x()
                    # self.iface.messageBar().pushMessage("Test", str(loc))
                else:
                    r = 0  # Uses as info to separate from IMP point to grid
                    writer = QgsVectorFileWriter(self.dir_poly, "CP1250", self.fields, self.prov.geometryType(),
                                                 self.prov.crs(), "ESRI shapefile")

                    if writer.hasError() != QgsVectorFileWriter.NoError:
                        self.iface.messageBar().pushMessage("Error when creating shapefile: ", str(writer.hasError()))
                    writer.addFeature(feature)
                    del writer

                if self.dlg.checkBoxOnlyBuilding.isChecked():  # Only building heights
                    provider = self.dsm_build.dataProvider()
                    filePath_dsm_build = str(provider.dataSourceUri())

                    if self.imid == 1:
                        gdalruntextdsm_build = gdalwarp_os_dep + ' -dstnodata -9999 -q -overwrite -te ' + str(x - r) + ' ' + str(y - r) + \
                                               ' ' + str(x + r) + ' ' + str(y + r) + ' -of GTiff "' + \
                                               filePath_dsm_build + '" "' + self.plugin_dir + '/data/clipdsm.tif"'
                    else:
                        gdalruntextdsm_build = gdalwarp_os_dep + ' -dstnodata -9999 -q -overwrite -cutline ' + self.dir_poly + \
                                               ' -crop_to_cutline -of GTiff "' + filePath_dsm_build + '" "' + \
                                               self.plugin_dir + '/data/clipdsm.tif"'

                    if sys.platform == 'win32':
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        subprocess.call(gdalruntextdsm_build, startupinfo=si)
                    else:
                        os.system(gdalruntextdsm_build)

                    # os.system(gdalruntextdsm_build)
                    dataset = gdal.Open(self.plugin_dir + '/data/clipdsm.tif')
                    dsm_array = dataset.ReadAsArray().astype(np.float)
                    sizex = dsm_array.shape[0]
                    sizey = dsm_array.shape[1]
                    dem_array = np.zeros((sizex, sizey))

                else:  # Both building ground heights
                    provider = self.dsm.dataProvider()
                    filePath_dsm = str(provider.dataSourceUri())
                    provider = self.dem.dataProvider()
                    filePath_dem = str(provider.dataSourceUri())

                    # # get raster source - gdalwarp
                    if self.imid == 1:
                        gdalruntextdsm = gdalwarp_os_dep + ' -dstnodata -9999 -q -overwrite -te ' + str(x - r) + ' ' + str(y - r) + \
                                               ' ' + str(x + r) + ' ' + str(y + r) + ' -of GTiff "' + \
                                               filePath_dsm + '" "' + self.plugin_dir + '/data/clipdsm.tif"'
                        gdalruntextdem = gdalwarp_os_dep + ' -dstnodata -9999 -q -overwrite -te ' + str(x - r) + ' ' + str(y - r) + \
                                               ' ' + str(x + r) + ' ' + str(y + r) + ' -of GTiff "' + \
                                               filePath_dem + '" "' + self.plugin_dir + '/data/clipdem.tif"'
                    else:
                        gdalruntextdsm = gdalwarp_os_dep + ' -dstnodata -9999 -q -overwrite -cutline ' + self.dir_poly + \
                                         ' -crop_to_cutline -of GTiff "' + filePath_dsm + \
                                         '" "' + self.plugin_dir + '/data/clipdsm.tif"'
                        gdalruntextdem = gdalwarp_os_dep + ' -dstnodata -9999 -q -overwrite -cutline ' + self.dir_poly + \
                                         ' -crop_to_cutline -of GTiff "' + filePath_dem + \
                                         '" "' + self.plugin_dir + '/data/clipdem.tif"'

                    if sys.platform == 'win32':
                        si = subprocess.STARTUPINFO()
                        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        subprocess.call(gdalruntextdsm, startupinfo=si)
                        subprocess.call(gdalruntextdem, startupinfo=si)
                    else:
                        os.system(gdalruntextdsm)
                        os.system(gdalruntextdem)

                    dataset = gdal.Open(self.plugin_dir + '/data/clipdsm.tif')
                    dsm_array = dataset.ReadAsArray().astype(np.float)
                    dataset2 = gdal.Open(self.plugin_dir + '/data/clipdem.tif')
                    dem_array = dataset2.ReadAsArray().astype(np.float)

                    if not (dsm_array.shape[0] == dem_array.shape[0]) & (dsm_array.shape[1] == dem_array.shape[1]):
                        QMessageBox.critical(None, "Error", "All grids must be of same pixel resolution")
                        return

                geotransform = dataset.GetGeoTransform()
                scale = 1 / geotransform[1]
                nd = dataset.GetRasterBand(1).GetNoDataValue()
                nodata_test = (dsm_array == nd)
                if self.dlg.checkBoxNoData.isChecked():
                    if np.sum(dsm_array) == (dsm_array.shape[0] * dsm_array.shape[1] * nd):
                        QgsMessageLog.logMessage(
                            "Grid " + str(f.attributes()[self.idx]) + " not calculated. Includes Only NoData Pixels",
                            level=QgsMessageLog.CRITICAL)
                        cal = 0
                    else:
                        dsm_array[dsm_array == nd] = np.mean(dem_array)
                        dem_array[dem_array == nd] = np.mean(dem_array)
                        cal = 1
                else:
                    if nodata_test.any():  # == True
                        QgsMessageLog.logMessage(
                            "Grid " + str(f.attributes()[self.idx]) + " not calculated. Includes NoData Pixels",
                            level=QgsMessageLog.CRITICAL)
                        cal = 0
                    else:
                        cal = 1

                if cal == 1:
                    # arr = np.array([f.attributes()[self.idx], -99, -99, -99, -99, -99, -99, -99])
                    # arrmat = np.vstack([arrmat, arr])
                # else:
                    immorphresult = imagemorphparam_v2(dsm_array, dem_array, scale, self.imid, self.degree, self.dlg, imp_point)

                    zH = immorphresult["zH"]
                    fai = immorphresult["fai"]
                    pai = immorphresult["pai"]
                    zMax = immorphresult["zHmax"]
                    zSdev = immorphresult["zH_sd"]

                    zd, z0 = rg.RoughnessCalcMany(self.rm, zH, fai, pai, zMax, zSdev)

                    # save to file
                    header = ' Wd pai   fai   zH  zHmax   zHstd zd z0'
                    numformat = '%3d %4.3f %4.3f %5.3f %5.3f %5.3f %5.3f %5.3f'
                    arr = np.concatenate((immorphresult["deg"], immorphresult["pai"], immorphresult["fai"],
                                        immorphresult["zH"], immorphresult["zHmax"], immorphresult["zH_sd"],zd,z0), axis=1)
                    np.savetxt(self.folderPath[0] + '/' + pre + '_' + 'IMPGrid_anisotropic_' + str(f.attributes()[self.idx]) + '.txt', arr,
                               fmt=numformat, delimiter=' ', header=header, comments='')

                    zHall = immorphresult["zH_all"]
                    faiall = immorphresult["fai_all"]
                    paiall = immorphresult["pai_all"]
                    zMaxall = immorphresult["zHmax_all"]
                    zSdevall = immorphresult["zH_sd_all"]
                    zdall, z0all = rg.RoughnessCalc(self.rm, zHall, faiall, paiall, zMaxall, zSdevall)

                    # If zd and z0 are lower than open country, set to open country
                    if zdall == 0.0:
                        zdall = 0.1
                    if z0all == 0.0:
                        z0all = 0.03

                    arr2 = np.array([[f.attributes()[self.idx], immorphresult["pai_all"], immorphresult["fai_all"], immorphresult["zH_all"],
                                      immorphresult["zHmax_all"], immorphresult["zH_sd_all"], zdall, z0all]])

                    arrmat = np.vstack([arrmat, arr2])

                dataset = None
                dataset2 = None
                dataset3 = None
                self.progress.emit()

            header = ' id  pai   fai   zH  zHmax   zHstd  zd  z0'
            numformat = '%3d %4.3f %4.3f %5.3f %5.3f %5.3f %5.3f %5.3f'
            arrmatsave = arrmat[1: arrmat.shape[0], :]
            np.savetxt(self.folderPath[0] + '/' + pre + '_' + 'IMPGrid_isotropic.txt', arrmatsave,
                                fmt=numformat, delimiter=' ', header=header, comments='')

            if self.dlg.addResultToGrid.isChecked():
                self.addattributes(self.vlayer, arrmatsave, header, pre)

            # Nas om hela loopen utforts, kan anvandas for att tilldela ret-variabeln resultatet av arbetet som ska
            # ska skickas tillbaka till image_morph_param.py
            if self.killed is False:
                self.progress.emit()
                ret = 1

        except Exception:
            # forward the exception upstream
            ret = 0
            errorstring = self.print_exception()
            #self.error.emit(e, traceback.format_exc())
            self.error.emit(errorstring)

        self.finished.emit(ret)
        # self.finished.emit(self.killed)

    def kill(self):
        self.killed = True

    def print_exception(self):
        exc_type, exc_obj, tb = sys.exc_info()
        f = tb.tb_frame
        lineno = tb.tb_lineno
        filename = f.f_code.co_filename
        linecache.checkcache(filename)
        line = linecache.getline(filename, lineno, f.f_globals)
        return 'EXCEPTION IN {}, \nLINE {} "{}" \nERROR MESSAGE: {}'.format(filename, lineno, line.strip(), exc_obj)

    def addattributes(self, vlayer, matdata, header, pre):
        # vlayer = self.vlayer
        current_index_length = len(vlayer.dataProvider().attributeIndexes())
        caps = vlayer.dataProvider().capabilities()

        if caps & QgsVectorDataProvider.AddAttributes:
            #vlayer.startEditing()
            line_split = header.split()
            for x in range(1, len(line_split)):

                vlayer.dataProvider().addAttributes([QgsField(pre + '_' + line_split[x], QVariant.Double)])

            attr_dict = {}

            for y in range(0, matdata.shape[0]):
                attr_dict.clear()
                idx = int(matdata[y, 0])
                for x in range(1, matdata.shape[1]):
                    attr_dict[current_index_length + x - 1] = float(matdata[y, x])
                #QMessageBox.information(None, "Error", str(line_split[x]))
                vlayer.dataProvider().changeAttributeValues({idx: attr_dict})

            vlayer.commitChanges()
            vlayer.updateFields()

            if self.iface.mapCanvas().isCachingEnabled():
                vlayer.setCacheImage(None)
            else:
                self.iface.mapCanvas().refresh()
        else:
            QMessageBox.critical(None, "Error", "Vector Layer does not support adding attributes")



    #ALLT UNDER DENNA KOMMENTAR FUNGERAR INTE aN OCH ANVaNDS INTE

    # def startParamWorker(self, dsm, dem, scale, mid, degree, f, idx, dlg):
    #     # create a new worker instance
    #     paramworker = ParamWorker(dsm, dem, scale, mid, degree, f, idx, dlg)
    #
    #     #self.dlg.runButton.setText('Cancel')
    #     #self.dlg.runButton.clicked.disconnect()
    #     self.dlg.runButton.clicked.connect(paramworker.kill)
    #     #self.dlg.closeButton.setEnabled(False)
    #
    #     # start the worker in a new thread
    #     paramthread = QThread(self)
    #     paramworker.moveToThread(paramthread)
    #     paramworker.finished.connect(self.paramworkerFinished)
    #     paramworker.error.connect(self.paramworkerError)
    #     #worker.progress.connect(self.progress_update)
    #     paramthread.started.connect(paramworker.run)
    #     paramthread.start()
    #     self.paramthread = paramthread
    #     self.paramworker = paramworker
    #
    # def paramworkerFinished(self, ret, f, idx):
    #     # clean up the worker and thread
    #     try:
    #         self.paramworker.deleteLater()
    #     except RuntimeError:
    #         pass
    #     self.paramthread.quit()
    #     self.paramthread.wait()
    #     self.paramthread.deleteLater()
    #
    #     if ret is not None:
    #          save to file
    #         header = ' Wd pai   fai   zH  zHmax   zHstd'
    #         numformat = '%3d %4.3f %4.3f %5.3f %5.3f %5.3f'
    #         arr = np.concatenate((ret["deg"], ret["pai"], ret["fai"],
    #                               ret["zH"], ret["zHmax"], ret["zH_sd"]), axis=1)
    #         np.savetxt(self.folderPath[0] + '/anisotropic_result_' + str(f.attributes()[idx]) + '.txt', arr,
    #                    fmt=numformat, delimiter=' ', header=header, comments='')
    #
    #         header = ' pai   zH    zHmax    zHstd'
    #         numformat = '%4.3f %5.3f %5.3f %5.3f'
    #         arr2 = np.array([[ret["pai_all"], ret["zH_all"], ret["zHmax_all"],
    #                           ret["zH_sd_all"]]])
    #         np.savetxt(self.folderPath[0] + '/isotropic_result_' + str(f.attributes()[idx]) + '.txt', arr2,
    #                    fmt=numformat, delimiter=' ', header=header, comments='')
    #
    #     else:
    #         notify the user that something went wrong
    #         self.dlg.runButton.setText('Run')
    #         self.dlg.runButton.clicked.disconnect()
    #         self.dlg.runButton.clicked.connect(self.start_progress)
    #         self.dlg.closeButton.setEnabled(True)
    #         self.dlg.progressBar.setValue(0)

    # def paramworkerError(self, e, exception_string):
    #     strerror = "ParamWorker thread raised an exception: " + str(e)
    #     QgsMessageLog.logMessage(strerror.format(exception_string), level=QgsMessageLog.CRITICAL)
