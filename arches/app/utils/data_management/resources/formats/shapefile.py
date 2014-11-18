import sys
import yaml
# from .. import utils
from django.contrib.gis.gdal import DataSource
from django.conf import settings
import os
from arches.app.models.models import Concepts
from arches.app.models.models import EntityTypes
from arches.app.models.concept import Concept
from django.db import connection

class Row(object):
    def __init__(self, *args):
        if len(args) == 0:
            self.resource_id = ''
            self.resourcetype = ''
            self.attributename = ''
            self.attributevalue = ''
            self.group_id = ''
        elif isinstance(args[0], list):
            self.resource_id = args[0][0].strip()
            self.resourcetype = args[0][1].strip()
            self.attributename = args[0][2].strip()
            self.attributevalue = args[0][3].strip().replace('\\n', '\n')
            self.group_id = args[0][4].strip()

    def __repr__(self):
        return ('"%s, %s, %s, %s"') % (self.resource_id, self. resourcetype, self. attributename, self.attributevalue)


class Group(object):
    def __init__(self, *args):
        if len(args) == 0:
            self.resource_id = ''
            self.group_id = ''
            self.rows = []
        elif isinstance(args[0], list):
            self.resource_id = args[0][0].strip()
            self.group_id = args[0][4].strip()
            self.rows = []   


class Resource(object):

    def __init__(self, *args):

        if len(args) == 0:
            self.resource_id = ''
            self.entitytypeid = ''
            self.groups = []
            self.nongroups = []

        elif isinstance(args[0], list):
            self.entitytypeid = args[0][1].strip()
            self.resource_id = args[0][0].strip()
            self.nongroups = []  
            self.groups = []


    def appendrow(self, row, group_id=None):
        if group_id != None:
            for group in self.groups:
                if group.group_id == group_id:
                    group.rows.append(row)
        else:
           self.nongroups.append(row)

    def __str__(self):
        return '{0},{1}'.format(self.resource_id, self.entitytypeid)


class ShapeReader():

    def load_file(self, shapefile):

        self.configs = self.parse_configs(shapefile)
        if self.configs:
            self.attr_map = self.configs['FIELD_MAP']

            self.concept_value_mappings = {}
            for field, entitytypeid in self.attr_map.iteritems():
                if entitytypeid.endswith('.E55'):
                    key, mapping = self.get_e55_concept_legacyoids(entitytypeid)
                    self.concept_value_mappings[key] = mapping
                else:
                    pass      
            
            self.auth_map = self.convert_uuid_map_to_conceptid_map(self.convert_aux_map_to_uuid_map(self.configs['AUXILIARY_MAP']))
            self.entitytypeid = self.configs['RESOURCE_TYPE']
            self.geom_type = self.configs['GEOM_TYPE']

            self.shp_data = self.read_shapefile(shapefile)

            shp_resource_info = self.collect_resource_info(
                    attr_mapping=self.attr_map,
                    auth_mapping=self.auth_map,
                    reader_output=self.shp_data,
                    geom_type=self.geom_type,
                    value_to_concept_label_mappings=self.concept_value_mappings)

            resources = []
            resource_id = ''
            group_id = ''
                
            for shp_dictionary in shp_resource_info:
                
                if (settings.LIMIT_ENTITY_TYPES_TO_LOAD == None or self.entitytypeid in settings.LIMIT_ENTITY_TYPES_TO_LOAD):
                    #take 1 dictionary at a time, and build a ShpResource from it
                    resource = Resource()
                    # populate the row with attributename and attributevalue
                    for key in shp_dictionary.keys():
                        if key is not None:
                            row = Row()
                            row.resource_id = resource_id
                            row.resourcetype = self.entitytypeid
                            row.attributename = key
                            row.attributevalue = shp_dictionary[key]
                            resource.appendrow(row)
                    resource.entitytypeid = self.entitytypeid
                    resources.append(resource)

            return resources


    def read(self, path):
        '''
        return the read shapefile
        '''
        shp_file = DataSource(os.path.abspath(path))
        return shp_file
        

    def get_layer_details(self, shp_file):
        '''
        Returns layer details of the given shapefile.
        Note that, we return a list even though 
            shapefiles are only allowed to have one layer
        '''
        layer_list = []
        for layer in shp_file:
            layer_list.append(layer)
        return layer_list
    

    def get_field_names(self, shp_file):
        '''
        return available fields of the passed shp file 
        '''
        fields = []
        # we get fields for all the layers
        layers = self.get_layer_details(shp_file)
        for layer in layers:
            fields.append(layer.fields)
        # returns a list of lists
        return fields
    

    def get_values(self, shp_file):
        '''
        returns a list of data associated with each field.
        field_values[n] is a list containing all the values for the 'n'th attribute
        '''
        field_names = self.get_field_names(shp_file)
        layer_0 = self.get_layer_details(shp_file)[0]
        field_values = []
    
        for field in field_names[0]: #consider the 0th layer
            field_values.append(layer_0.get_fields(field))
        return field_values
    

    def get_wkt_values(self, shp_file):
        '''
        returns geographic data associated with the shapefile(shapes) in WKT format.
        These value will be added to the json file 
        '''
        wkt_list=[]
        #return geo_data in wkt format
        for resource in self.get_layer_details(shp_file)[0]:
            wkt_list.append(resource.geom.wkt)
        return wkt_list


    def parse_configs(self, shapefile):
        '''
        Takes a shapefile and reads a config file with the same basename.
        Returns a dictionary with configuration for creating resources from shapefile records
        '''
        result = None
        try:
            config_file = os.path.join(os.path.dirname(shapefile), os.path.basename(shapefile).split('.')[0] + '.config')
            if os.path.exists(config_file):
                result = yaml.load(open(config_file, 'r'))
                result['AUXILIARY_MAP'] = {}
            #AUXILIARY_MAP = {"NAME TYPE.E55" : "Primary","EXTERNAL XREF TYPE.E55" : "Legacy System"}
            #The auxiliary_map was Tharindus strategy to map concepts to their labels. This is not being implemented yet
        except:
            print "config file is missing or improperly named. Make sure you have config file with the same basename as your shapefile and the extension .config"

        return result


    def get_concept_uuid_for_aux_map_entry(self,concept_name,concept_value):
        '''
        Reads concept labels(prefLabels) given in AUXILIARY_MAP and returns a list of conceptids.

        '''
        concept = None
        try:
            concept = Concepts.objects.get(legacyoid = concept_name)
        except:
            print "No Concept found with the name %s"%concept_name
        if concept is not None:
            concept_graph = Concept().get(id=concept.pk, include_subconcepts=True, include=['label'])
   
            if concept_graph.subconcepts:
                for subconcept  in concept_graph.subconcepts[0].subconcepts:
                    for value in subconcept.values:

                        if value.type == "prefLabel" and value.value == concept_value:
                            return subconcept.id

                print '[ERROR]: %s is not found in %s'%(concept_value,concept_name)
            return
        

    def convert_aux_map_to_uuid_map(self,aux_map):
        '''
        converts the AUX_MAP values into uuid
        '''
        converted_aux_map = {}
        for entry in aux_map.keys():
            value = self.get_concept_uuid_for_aux_map_entry(entry, aux_map[entry])
            if value is not None:
                converted_aux_map[entry] = value
        
        return converted_aux_map  
    

    def convert_uuid_map_to_conceptid_map(self,uuid_map):
        '''
        convert an uuid dictionary into conceptId dictionary because
        data.domains should be populated with conceptId values
        ''' 
        conceptid_map = {}
        sql_template = """'SELECT concepts.legacyoid FROM concepts.concepts WHERE concepts.conceptid = '"""
        cursor = connection.cursor()
        for key in uuid_map.keys():
            cursor.execute(sql_template+uuid_map[key]+"'")
            conceptid_map[key] = cursor.fetchone()[0]
            
        return conceptid_map  


    def get_e55_concept_legacyoids(self, e55_type):
        concept = EntityTypes.objects.get(pk=e55_type).conceptid
        concept_graph = Concept().get(id=concept.pk, include_relatedconcepts=True, include=['label'])
        values_to_legacy = []
        cursor = connection.cursor()
        if len(concept_graph.relatedconcepts) > 0:
            for value in concept_graph.relatedconcepts:
                if value.type == "prefLabel":
                    sql = "SELECT concepts.legacyoid FROM concepts.concepts WHERE concepts.conceptid = '{0}'".format(value.conceptid)
                    cursor.execute(sql)
                    legacyoid = str(cursor.fetchone()[0])
                    values_to_legacy.append({value.value:legacyoid})
        return e55_type, values_to_legacy


    # Now build a list of dictionaries, one per record
    def collect_resource_info(self, attr_mapping, auth_mapping, reader_output, geom_type, value_to_concept_label_mappings, break_on_error=True):
        dict_list=[] # list of dictionaries
        attr_names = reader_output[0]
        attr_vals = reader_output[1][0:-1] # get all attribute values except the geom_wkt values
        geom_values = reader_output[1][-1] # last index because we append wkt values at the end

        '''
        first, add the attribute values to the dictionary
        and then add authority details. Because shapefile data does not 
        contain authority details but the authority mapping
        is defined by the user and passed in a separate dictionary
        '''      
        errors = []
        for record_index in range (0, len(attr_vals[0])): #len(attr_vals[0]) equals to the number of records
            record_dictionary= {} # i th dictionary
            for attr in attr_names[0]: # loops for (number of attributes) times
                #get the index of the selected attribute
                attr_index = attr_names[0].index(attr)
                #add the key/value pair retrieved from the attr_mapping
                entitytypeid = attr_mapping.get(attr)
                label = attr_vals[attr_index][record_index]
                found_match = False

                if type(entitytypeid) == str:
                    if entitytypeid.endswith('.E55'):
                        count = 0
                        for mapping in value_to_concept_label_mappings[entitytypeid]:
                            count += 1
                            if unicode(label) == mapping.keys()[0]:
                                label = mapping[label]
                                count = 0
                                break
                        if count == len(value_to_concept_label_mappings[entitytypeid]):
                            errors.append('shapefile record {0}: "{1}", Does not match any available {2} concept value\n'.format(str(record_index), label, entitytypeid))
                        
                record_dictionary[entitytypeid] = label
            
            record_dictionary.update(auth_mapping)

            record_dictionary[geom_type] = geom_values[record_index] 
            dict_list.append(record_dictionary)

        # if len(errors) > 0:
        #     utils.write_to_file(os.path.join(settings.PACKAGE_ROOT, 'logs', 'shapefile_loading_errors.txt'), '\n'.join(errors))
        #     print 'There were errors matching some values to concepts, please see {0} for details'.format(os.path.join(settings.PACKAGE_ROOT, 'logs', 'shapefile_loading_errors.txt'))
        #     if break_on_error:
        #         sys.exit(101)
        return dict_list


    def read_shapefile(self, shp_path):
        '''
        The following method takes the location of a shapefile returns all data as a single tuple.
        '''

        shapefile = self.read(shp_path)
        field_names = self.get_field_names(shapefile)
        field_values_and_geom_wkt = self.get_values(shapefile)
        geom_wkt_values = self.get_wkt_values(shapefile)
        
        # since it is desirable to pass field_values and wkt data in a single list, we combine the two lists
        field_values_and_geom_wkt.append(geom_wkt_values) #the last item of field_values is a list containing wkt geom values
        
        return (field_names, field_values_and_geom_wkt)