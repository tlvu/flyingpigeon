"""
Process for spatial analog calculations.

Author: David Huard (huard.david@ouranos.ca),
"""

from flyingpigeon.log import init_process_logger
from flyingpigeon.utils import archiveextract
from flyingpigeon.utils import rename_complexinputs
from flyingpigeon.utils import get_values
from flyingpigeon.ocgis_module import call
from shapely.geometry import Point

from pywps import Process
from pywps import LiteralInput
from pywps import ComplexInput, ComplexOutput
from pywps import Format
from pywps.app.Common import Metadata

from datetime import datetime as dt
import os

from ocgis import FunctionRegistry
from ..ocgisDissimilarity import Dissimilarity, metrics

FunctionRegistry.append(Dissimilarity)

import logging
LOGGER = logging.getLogger("PYWPS")


class SpatialAnalogProcess(Process):
    def __init__(self):
        inputs = [
            ComplexInput('candidate', 'Candidate netCDF dataset',
                         abstract='NetCDF files or archive (tar/zip) containing netcdf '
                                  'files storing the candidate indices.',
                         metadata=[Metadata('Info')],
                         min_occurs=1,
                         max_occurs=1000,
                         supported_formats=[
                             Format('application/x-netcdf'),
                             Format('application/x-tar'),
                             Format('application/zip'),
                         ]),

            ComplexInput('target', 'Target netCDF dataset',
                         abstract='NetCDF files or archive (tar/zip) '
                                  'containing netcdf files storing the '
                                  'target indices.',
                         metadata=[Metadata('Info')],
                         min_occurs=1,
                         max_occurs=1000,
                         supported_formats=[
                             Format('application/x-netcdf'),
                             Format('application/x-tar'),
                             Format('application/zip'),
                         ]),

            LiteralInput('location', 'Target coordinates (lon,lat)',
                         abstract="Geographical coordinates (lon,lat) of the target location.",
                         data_type='string',
                         min_occurs=1,
                         max_occurs=1,
                         ),

            LiteralInput('indices', 'Indices',
                         abstract="One or more climate indices to use for the comparison.",
                         data_type='string',
                         min_occurs=1,
                         max_occurs=5,
                         ),

            LiteralInput('dist', "Distance",
                         abstract="Dissimilarity metric comparing distributions.",
                         data_type='string',
                         min_occurs=0,
                         max_occurs=1,
                         default='kldiv',
                         allowed_values=metrics,
                         ),

            LiteralInput('dateStartCandidate', 'Candidate start date',
                         abstract="Beginning of period (YYYY-MM-DD) for candidate data. "
                                  "Defaults to first entry.",
                         data_type='string',
                         min_occurs=0,
                         max_occurs=1,
                         default='',
                         ),

            LiteralInput('dateEndCandidate', 'Candidate end date',
                         abstract="End of period (YYYY-MM_DD) for candidate data. Defaults to last entry.",
                         data_type='string',
                         min_occurs=0,
                         max_occurs=1,
                         default='',
                         ),

            LiteralInput('dateStartTarget', 'Target start date',
                         abstract="Beginning of period (YYYY-MM-DD) for target "
                                  "data. "
                                  "Defaults to first entry.",
                         data_type='string',
                         min_occurs=0,
                         max_occurs=1,
                         default='',
                         ),

            LiteralInput('dateEndTarget', 'Target end date',
                         abstract="End of period (YYYY-MM_DD) for target data. "
                                  "Defaults to last entry.",
                         data_type='string',
                         min_occurs=0,
                         max_occurs=1,
                         default='',
                         ),
        ]

        outputs = [

            ComplexOutput('output_netcdf', 'Dissimilarity values',
                          abstract="Dissimilarity between target at selected "
                                   "location and candidate distributions over the entire grid.",
                          as_reference=True,
                          supported_formats=[Format('application/x-netcdf')]
                          ),

            ComplexOutput('output_log', 'Logging information',
                          abstract="Collected logs during process run.",
                          as_reference=True,
                          supported_formats=[Format('text/plain')]
                          ),
        ]

        super(SpatialAnalogProcess, self).__init__(
            self._handler,
            identifier="spatial_analog",
            title="Spatial analog of a target climate.",
            abstract="Spatial analogs based on the comparison of climate "
                     "indices. The algorithm compares the distribution of the "
                     "target indices with the distribution of spatially "
                     "distributed candidate indices and returns a value  "
                     "measuring the dissimilarity between both distributions.",
            version="0.1",
            metadata=[
                Metadata('Doc', 'http://flyingpigeon.readthedocs.io/en/latest/'),
            ],
            inputs=inputs,
            outputs=outputs,
            status_supported=True,
            store_supported=True,
        )

    def _handler(self, request, response):
        tic = dt.now()
        init_process_logger('log.txt')
        response.outputs['output_log'].file = 'log.txt'

        LOGGER.info('Start process')
        response.update_status('execution started at : {}'.format(tic, 5))

        ######################################
        # Read inputs
        ######################################
        try:
            response.update_status('read input parameter : {}'.format(dt.now()), 5)

            candidate = archiveextract(resource=rename_complexinputs(
                request.inputs['candidate']))
            target = archiveextract(resource=rename_complexinputs(
                request.inputs['target']))
            location = request.inputs['location'][0].data
            indices = [el.data for el in request.inputs['indices']]
            dist = request.inputs['dist'][0].data
            dateStartCandidate = request.inputs['dateStartCandidate'][0].data
            dateEndCandidate = request.inputs['dateEndCandidate'][0].data
            dateStartTarget = request.inputs['dateStartTarget'][0].data
            dateEndTarget = request.inputs['dateEndTarget'][0].data

            LOGGER.info('input parameters set')
            response.update_status('Read in and convert the arguments', 5)

        except Exception as e:
            msg = 'failed to read input parameter {} {} {}'.format(e,
                            request.inputs['candidate'],request.inputs['target'])
            LOGGER.error(msg)
            raise Exception(msg)


        ######################################
        # Process inputs
        ######################################

        try:
            point = Point(*map(float, location.split(',')))
            dateStartCandidate = dt.strptime(dateStartCandidate, '%Y-%m-%d')
            dateEndCandidate = dt.strptime(dateEndCandidate, '%Y-%m-%d')
            dateStartTarget = dt.strptime(dateStartTarget, '%Y-%m-%d')
            dateEndTarget = dt.strptime(dateEndTarget, '%Y-%m-%d')

        except Exception as e:
            msg = 'failed to process inputs {} '.format(e)
            LOGGER.error(msg)
            raise Exception(msg)

        LOGGER.debug("init took {}".format(dt.now() - tic ) )
        response.update_status('Read in and convert the arguments', 5)

        ######################################
        # Extract target time series
        ######################################

        try:
            target_ts = call(resource=target,
                             geom=point,
                             variables=indices,
                             time_range=[dateStartTarget, dateEndTarget],
                             select_nearest=True)

            target_values = get_values(target_ts)

        except Exception as e:
            LOGGER.debug('target extraction failed {}'.format(e))

        response.update_status('Extracted target time series', 10)

        ######################################
        # Compute dissimilarity metric
        ######################################

        try:
            output = call(resource=candidate,
                          calc=[{'func': 'dissimilarity', 'name': 'spatial_analog',
                                 'kwds': {'algo': dist, 'target': target_values,
                                          'candidate': indices}}],
                          time_range=[dateStartCandidate, dateEndCandidate],
                          )

        except Exception as e:
            msg = 'Spatial analog failed: {}'.format(e)
            LOGGER.exception(msg)
            raise Exception(msg)

        LOGGER.debug("spatial_analog took {}.".format(dt.now() - tic))
        response.update_status('preparing output', 99)



        response.outputs['output_netcdf'] = output
        response.update_status('execution ended', 100)
        LOGGER.debug("total execution took {}".format( dt.now() - tic) )
        return response

