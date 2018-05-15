# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from aria.utils.formatting import safe_repr
from aria.parser.validation import Issue
from .parameters import (coerce_parameter_value, convert_parameter_definitions_to_values)
from aria.utils.collections import (merge, deepcopy_with_locators, OrderedDict)
from aria.parser.presentation import get_locator
from aria.parser.exceptions import InvalidValueError

ALLOWED_PROPERTY_MAPPINGS = ['get_input' , 'get_property']

def convert_interface_definition_from_type_to_raw_template(context, presentation):                  # pylint: disable=invalid-name
    raw = OrderedDict()

    # Copy default values for inputs
    interface_inputs = presentation._get_inputs(context)
    if interface_inputs is not None:
        raw['inputs'] = convert_parameter_definitions_to_values(context, interface_inputs)

    # Copy operations
    operations = presentation._get_operations(context)
    if operations:
        for operation_name, operation in operations.iteritems():
            raw[operation_name] = OrderedDict()
            description = operation.description
            if description is not None:
                raw[operation_name]['description'] = deepcopy_with_locators(description._raw)
            implementation = operation.implementation
            if implementation is not None:
                raw[operation_name]['implementation'] = deepcopy_with_locators(implementation._raw)
            inputs = operation.inputs
            if inputs is not None:
                raw[operation_name]['inputs'] = convert_parameter_definitions_to_values(context,
                                                                                        inputs)

    return raw

def assign_raw_inputs(context, raw, assignments, definitions, interface_name, operation_name,
                      presentation):
    if assignments is None:
        assignments = {}
    if definitions is None:
        definitions = {}

    # Make sure we have the dict
    if ('inputs' not in raw) or (raw['inputs'] is None):
        raw['inputs'] = OrderedDict()

    # Defaults
    for input_name, definition in definitions.iteritems():
        if ('default' in definition._raw) and (input_name not in raw['inputs']):
            raw['inputs'][input_name] = coerce_parameter_value(context, definition, definition,
                                                               definition.default, 'default')

    # Assign inputs
    for input_name, assignment in assignments.iteritems():
        if (not context.presentation.configuration.get('tosca.adhoc_inputs', True)) and \
            (input_name not in definitions):
            if operation_name is not None:
                context.validation.report(
                    u'interface definition "{0}" assigns a value to an unknown operation input'
                    u' "{1}.{2}" in "{3}"'
                    .format(interface_name, operation_name, input_name, presentation._fullname),
                    locator=assignment._locator, level=Issue.BETWEEN_TYPES)
            else:
                context.validation.report(
                    u'interface definition "{0}" assigns a value to an unknown input "{1}" in "{2}"'
                    .format(interface_name, input_name, presentation._fullname),
                    locator=assignment._locator, level=Issue.BETWEEN_TYPES)

        definition = definitions.get(input_name) # Could be None!
        raw['inputs'][input_name] = coerce_parameter_value(context, assignment, definition,
                                                           assignment.value)


def convert_interface_definition_from_type_to_template(context, presentation, container):
    from ..assignments import InterfaceAssignment

    if isinstance(presentation, InterfaceAssignment):
        # Nothing to convert, so just clone
        return presentation._clone(container)

    raw = convert_interface_definition_from_type_to_raw_template(context, presentation)
    return InterfaceAssignment(name=presentation._name, raw=raw, container=container)


def merge_interface(context, presentation, interface_assignment, our_interface_assignment,
                    interface_definition, interface_name):
    # Assign/merge interface inputs
    assign_raw_inputs(context, interface_assignment._raw, our_interface_assignment.inputs,
                      interface_definition._get_inputs(context), interface_name, None, presentation)

    our_operation_templates = our_interface_assignment.operations # OperationAssignment
    if our_operation_templates is None:
        our_operation_templates = {}

    # OperationDefinition or OperationAssignment:
    operation_definitions = interface_definition._get_operations(context) \
        if hasattr(interface_definition, '_get_operations') else interface_definition.operations
    if operation_definitions is None:
        operation_definitions = {}

    # OperationAssignment:
    for operation_name, our_operation_template in our_operation_templates.iteritems():
        operation_definition = operation_definitions.get(operation_name) # OperationDefinition

        our_input_assignments = our_operation_template.inputs
        our_implementation = our_operation_template.implementation

        if operation_definition is None:
            context.validation.report(
                u'interface definition "{0}" refers to an unknown operation "{1}" in "{2}"'
                .format(interface_name, operation_name, presentation._fullname),
                locator=our_operation_template._locator, level=Issue.BETWEEN_TYPES)

        # Make sure we have the dict
        if (operation_name not in interface_assignment._raw) \
            or (interface_assignment._raw[operation_name] is None):
            interface_assignment._raw[operation_name] = OrderedDict()

        if our_implementation is not None:
            interface_assignment._raw[operation_name]['implementation'] = \
                deepcopy_with_locators(our_implementation._raw)

        # Assign/merge operation inputs
        input_definitions = operation_definition.inputs \
            if operation_definition is not None else None
        assign_raw_inputs(context, interface_assignment._raw[operation_name],
                          our_input_assignments, input_definitions, interface_name,
                          operation_name, presentation)

def validate_required_inputs(context, presentation, assignment, definition, original_assignment,
                             interface_name, operation_name=None):
    # The validation of the `required` field of inputs that belong to operations and interfaces
    # (as opposed to topology template and workflow inputs) is done only in the parsing stage.
    # This reasoning follows the TOSCA spirit, where anything that is declared as required in the
    # type, must be assigned in the corresponding template.

    # Note: InterfaceDefinition need _get_inputs, but OperationDefinition doesn't
    input_definitions = definition._get_inputs(context) \
        if hasattr(definition, '_get_inputs') \
        else definition.inputs
    if input_definitions:
        for input_name, input_definition in input_definitions.iteritems():
            if input_definition.required:
                prop = assignment.inputs.get(input_name) \
                    if ((assignment is not None) and (assignment.inputs is not None)) else None
                value = prop.value if prop is not None else None
                value = value.value if value is not None else None
                if value is None:
                    if operation_name is not None:
                        context.validation.report(
                            u'interface definition "{0}" does not assign a value to a required'
                            u' operation input "{1}.{2}" in "{3}"'
                            .format(interface_name, operation_name, input_name,
                                    presentation._fullname),
                            locator=get_locator(original_assignment, presentation._locator),
                            level=Issue.BETWEEN_TYPES)
                    else:
                        context.validation.report(
                            u'interface definition "{0}" does not assign a value to a required'
                            u' input "{1}" in "{2}"'
                            .format(interface_name, input_name, presentation._fullname),
                            locator=get_locator(original_assignment, presentation._locator),
                            level=Issue.BETWEEN_TYPES)

    if operation_name is not None:
        return

    assignment_operations = assignment.operations
    operation_definitions = definition._get_operations(context)
    if operation_definitions:
        for operation_name, operation_definition in operation_definitions.iteritems():
            assignment_operation = assignment_operations.get(operation_name) \
                if assignment_operations is not None else None
            original_operation = \
                original_assignment.operations.get(operation_name, original_assignment) \
                if (original_assignment is not None) \
                and (original_assignment.operations is not None) \
                else original_assignment
            validate_required_inputs(context, presentation, assignment_operation,
                                     operation_definition, original_operation, interface_name,
                                     operation_name)


def check_if_input_value_is_valid(context, presentation, input_value):
    check_input_property = _get_input(context, input_value)
    substitution_node_type = presentation._container._get_type(context)

    if check_input_property is None:
        context.validation.report(
            u'field {0} is not a valid input name referred in substitution mapping property '
            u'in node type "{substitution_type}"'.format(
                input_value, substitution_type=substitution_node_type._name),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)

        raise InvalidValueError(
            u'function "get_input" argument does not contain a valid input name: {0} in substitution_mappings section'
                .format(safe_repr(input_value),
                        locator=presentation._locator))

def check_if_property_value_is_valid(context, presentation, property_value):
    pass



def validate_property_mapping_for_inputs(context, presentation):

    our_input = presentation._raw[0]
    print "input name --> ", our_input
    check_if_input_value_is_valid(context, presentation, our_input)
    return

def validate_property_mapping_for_node_template_and_property(context, presentation):

    mapped_node_template_name = presentation._raw[0]
    mapped_property_name = presentation._raw[1]
    substitution_node_type = presentation._container._get_type(context)

    print "Node Template name -->", mapped_node_template_name
    print("PropertyName --> ", mapped_property_name)
    # Validate that the capability in substitution_mapping is declared in the corresponding
    # node template
    node_template = _get_node_template(context, presentation)
    if node_template is None:
        _report_missing_node_template(context, presentation, field='property')
        return

    if node_template is not None:
        for key in node_template._get_property_values(context):
            print key
            if key == mapped_property_name:
                break
        else:
            context.validation.report(
                u'substitution mapping property "{0}" does not have a valid property value "{1}"'
                u' mapped to node "{2}" declared in node type "{3}"'.format(
                    presentation._name, mapped_property_name, mapped_node_template_name, substitution_node_type._name),
                locator=presentation._locator, level=Issue.BETWEEN_TYPES)
            return

def validate_property_mapping_for_node_template_along_with_reqOrCap_and_property(context, presentation):

    mapped_node_template_name = presentation._raw[0]
    mapped_reqOrCap = presentation._raw[1]
    mapped_property_name = presentation._raw[2]

    print "Node Template name -->", mapped_node_template_name
    print "ReqOrCap -->", mapped_reqOrCap
    print("PropertyName --> ", mapped_property_name)
    substitution_node_type = presentation._container._get_type(context)
    # print ("Substitution mapping node type --> ", substitution_node_type)
    node_template = _get_node_template(context, presentation)


    if node_template is None:
        _report_missing_node_template(context, presentation, field='property')
        return

    cap_status = False
    node_template_capabilities = node_template._get_capabilities(context)
    if node_template_capabilities is not None:
        node_template_capability = node_template_capabilities.get(mapped_reqOrCap)
        if node_template_capability is None:
            #context.validation.report(
            #    u'substitution mapping capability "{0}" refers to an unknown '
            #    u'capability of node template "{1}": {mapped_reqOrCap}'.format(
            #        presentation._name, node_template._name,
            #        mapped_reqOrCap=safe_repr(mapped_reqOrCap)),
            #    locator=presentation._locator, level=Issue.BETWEEN_TYPES)
            #return
            pass
        else:
            cap_status=True

    req_status = False
    node_template_requirements = node_template._get_requirements(context)
    if node_template_requirements is not None:
        if isinstance(node_template_requirements, list):
            for aRequirement in node_template_requirements:
                for req_name in aRequirement:
                    if req_name == mapped_reqOrCap:
                        req_status = True
                        print "inside aRequirement&&&&&&&&&&&&&"
                        break
                else:
                    print "requirements are not present in the template "
                    # context.validation.report(
                    #     u'substitution mapping requirement "{0}" refers to an unknown requirement of node '
                    #     u'template "{1}": {mapped_requirement_name}'.format(
                    #         presentation._name, node_template._name,
                    #         mapped_requirement_name=safe_repr(mapped_reqOrCap)),
                    #     locator=presentation._locator, level=Issue.BETWEEN_TYPES)
                    # return

    if cap_status == False or req_status == False:
        print "Either capability or requirement is not present in the substitution mapping section"
        context.validation.report(
            u'substitution mapping requirement / capability"{0}" refers to an unknown requirement of node '
            u'template "{1}": {mapped_requirement_name}'.format(
                presentation._name, node_template._name,
                mapped_requirement_name=safe_repr(mapped_reqOrCap)),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)


    print "done"


def validate_substitution_mappings_property(context, presentation):

    # Validate that the capability in substitution_mapping is defined in the substitution node type
    print "Inside property Validation method of substitution mapping"
    substitution_node_type = presentation._container._get_type(context)
    #print ("Substitution mapping node type --> ", substitution_node_type)
    if substitution_node_type is None:
        return

    # validate the keys of node type in substitution mapping section
    # for prop_name in substitution_node_type._get_properties(context):
    #     if prop_name == presentation._name:
    #       break
    # else:
    #     context.validation.report(
    #         u'substitution mapping requirement "{0}" is not declared in node type "{1}"'.format(
    #             presentation._name, substitution_node_type._name),
    #         locator=presentation._locator, level=Issue.BETWEEN_TYPES)
    #     return


    if isinstance(presentation._raw, dict):
        for actual_key, property_value in presentation._raw.iteritems():
            if (actual_key in ALLOWED_PROPERTY_MAPPINGS):
                if ("get_input" == actual_key):
                    check_if_input_value_is_valid(context, presentation, property_value)
                elif ("get_property" == actual_key):
                    check_if_property_value_is_valid(context, presentation, property_value)

            else:
                context.validation.report(
                    u'field {0} is not allowed in substitution mapping property '
                    u'is not declared in node type "{substitution_type}"'.format(
                        actual_key, substitution_type=substitution_node_type._name),
                    locator=presentation._locator, level=Issue.BETWEEN_TYPES)

    elif isinstance(presentation._raw, list):
        size = len(presentation._raw)
        print "Size of Property Mapping: {}".format(size)
        if size == 1:
            validate_property_mapping_for_inputs(context, presentation)
        if size == 2:
            validate_property_mapping_for_node_template_and_property(context, presentation)
        if size == 3:
            validate_property_mapping_for_node_template_along_with_reqOrCap_and_property(context, presentation)



def validate_substitution_mappings_attribute(context, presentation):
    # Validate that the capability in substitution_mapping is defined in the substitution node type
    #print "Inside attribue Validation method of substitution mapping"
    substitution_node_type = presentation._container._get_type(context)
    #print ("Substitution mapping node type --> ", substitution_node_type)
    if substitution_node_type is None:
        return


def validate_substitution_mappings_interface(context, presentation, type_name = "node template"):
    # Validate that the capability in substitution_mapping is defined in the substitution node type
    #print "Inside intrface Validation method of substitution mapping"
    #print "Interfce presetation -->", presentation.__dict__
    #print "Interfce contaiiner -->", presentation._container.__dict__

    template_interfaces = OrderedDict()
    substitution_node_type = presentation._container._get_type(context)         # aka the_type  --> NodeType
    #print ("Substitution mapping interface node type -------------------> ", substitution_node_type)
    #print ("Substitution mapping interface node type dict-------------------> ", substitution_node_type.__dict__)
    #print ("Substitution mapping interface node type container -------------------> ", substitution_node_type.__dict__['_container'])

    if substitution_node_type is None:
        return

    substitution_type_interfaces = substitution_node_type._get_interfaces(context)   #aka interface_definitions

    substitution_type_interface = substitution_type_interfaces.get(presentation._name)

    print "Substitution type interface ------------->", substitution_type_interface
    if substitution_type_interface is None:
        context.validation.report(
            u'substitution mapping interface "{0}" '
            u'is not declared in node type "{substitution_type}"'.format(
                presentation._name, substitution_type=substitution_node_type._name),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)
        return


    """
    template_interfaces = OrderedDict()

    the_type = presentation._get_type(context)  # NodeType, RelationshipType, GroupType
    # InterfaceDefinition (or InterfaceAssignment in the case of RelationshipTemplate):
    interface_definitions = the_type._get_interfaces(context) if the_type is not None else None
    """
    """
    operation_name = presentation._raw[0]
    our_interface_name = presentation._raw[1]
    # Copy over interfaces from the type (will initialize inputs with default values)
    if substitution_type_interfaces:
        for interface_name, interface_definition in substitution_type_interfaces.iteritems():
            # Note that in the case of a RelationshipTemplate, we will already have the values as
            # InterfaceAssignment.
            if interface_name == our_interface_name:
               operation_definitions = interface_definition._get_operations(context)
               operation_definition = operation_definitions.get(operation_name)
               if operation_definition is None:
                  context.validation.report(
                    u'interface definition "{0}" refers to an unknown operation "{1}" in "{2}"'
                    .format(interface_name, operation_name, presentation._fullname),
                    locator=presentation._locator,level=Issue.BETWEEN_TYPES)

          #  template_interfaces[interface_name] = \
          #      convert_interface_definition_from_type_to_template(context, interface_definition,
          #                                                         presentation)
    """
    """
    # Fill in our interfaces
    our_interface_assignments = presentation.interfaces
    if our_interface_assignments:
        # InterfaceAssignment:
        for interface_name, our_interface_assignment in our_interface_assignments.iteritems():
            if interface_name in template_interfaces:
                interface_assignment = template_interfaces[interface_name]  # InterfaceAssignment
                # InterfaceDefinition (or InterfaceAssignment in the case of RelationshipTemplate):
                interface_definition = substitution_type_interfaces[interface_name]
                merge_interface(context, presentation, interface_assignment,
                                our_interface_assignment, interface_definition, interface_name)
            else:
                context.validation.report(
                    u'interface definition "{0}" not declared at {1} "{2}" in "{3}"'
                        .format(interface_name, type_name, presentation.type, presentation._fullname),
                    locator=our_interface_assignment._locator, level=Issue.BETWEEN_TYPES)
   
    # Check that there are no required inputs that we haven't assigned
    for interface_name, interface_template in template_interfaces.iteritems():
        if interface_name in interface_definitions:
            # InterfaceDefinition (or InterfaceAssignment in the case of RelationshipTemplate):
            interface_definition = interface_definitions[interface_name]
            our_interface_assignment = our_interface_assignments.get(interface_name) \
                if our_interface_assignments is not None else None
            validate_required_inputs(context, presentation, interface_template,
                                     interface_definition, our_interface_assignment, interface_name)

    return template_interfaces
    """



def validate_substitution_mappings_requirement(context, presentation):
    # Validate that the requirement in substitution_mapping is defined in the substitution node type
    print "Requiremnt presetation -->", presentation.__dict__
    print "*******Requirement container -->", presentation._container.__dict__
    substitution_node_type = presentation._container._get_type(context)
    print ("Substitution mapping reqruiement node type -------------------> ", substitution_node_type)
    print ("Substitution mapping node requirement type dict-------------------> ", substitution_node_type.__dict__)
    print ("Substitution mapping node requirement type container -------------------> ", substitution_node_type.__dict__['_container'])
    if substitution_node_type is None:
        return
    for req_name, req in substitution_node_type._get_requirements(context):
        if req_name == presentation._name:
            substitution_type_requirement = req
            break
    else:
        context.validation.report(
            u'substitution mapping requirement "{0}" is not declared in node type "{1}"'.format(
                presentation._name, substitution_node_type._name),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)
        return

    if not _validate_mapping_format(presentation):
        _report_invalid_mapping_format(context, presentation, field='requirement')
        return

    # Validate that the mapped requirement is defined in the corresponding node template
    node_template = _get_node_template(context, presentation)
    if node_template is None:
        _report_missing_node_template(context, presentation, field='requirement')
        return
    mapped_requirement_name = presentation._raw[1]
    for req_name, req in node_template._get_requirements(context):
        if req_name == mapped_requirement_name:
            node_template_requirement = req
            break
    else:
        context.validation.report(
            u'substitution mapping requirement "{0}" refers to an unknown requirement of node '
            u'template "{1}": {mapped_requirement_name}'.format(
                presentation._name, node_template._name,
                mapped_requirement_name=safe_repr(mapped_requirement_name)),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)
        return

    # Validate that the requirement's capability type in substitution_mapping is derived from the
    # requirement's capability type in the corresponding node template
    substitution_type_requirement_capability_type = \
        substitution_type_requirement._get_capability_type(context)
    node_template_requirement_capability_type = \
        node_template_requirement._get_capability(context)[0]
    if not substitution_type_requirement_capability_type._is_descendant(
            context, node_template_requirement_capability_type):
        context.validation.report(
            u'substitution mapping requirement "{0}" of capability type "{1}" is not a descendant '
            u'of the mapped node template capability type "{2}"'.format(
                presentation._name,
                substitution_type_requirement_capability_type._name,
                node_template_requirement_capability_type._name),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)


def validate_substitution_mappings_capability(context, presentation):
    # Validate that the capability in substitution_mapping is defined in the substitution node type
    substitution_node_type = presentation._container._get_type(context)
    if substitution_node_type is None:
        return
    substitution_type_capabilities = substitution_node_type._get_capabilities(context)
    substitution_type_capability = substitution_type_capabilities.get(presentation._name)
    if substitution_type_capability is None:
        context.validation.report(
            u'substitution mapping capability "{0}" '
            u'is not declared in node type "{substitution_type}"'.format(
                presentation._name, substitution_type=substitution_node_type._name),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)
        return

    if not _validate_mapping_format(presentation):
        _report_invalid_mapping_format(context, presentation, field='capability')
        return

    # Validate that the capability in substitution_mapping is declared in the corresponding
    # node template
    node_template = _get_node_template(context, presentation)
    if node_template is None:
        _report_missing_node_template(context, presentation, field='capability')
        return
    mapped_capability_name = presentation._raw[1]
    node_template_capability = node_template._get_capabilities(context).get(mapped_capability_name)

    if node_template_capability is None:
        context.validation.report(
            u'substitution mapping capability "{0}" refers to an unknown '
            u'capability of node template "{1}": {mapped_capability_name}'.format(
                presentation._name, node_template._name,
                mapped_capability_name=safe_repr(mapped_capability_name)),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)
        return

    # Validate that the capability type in substitution_mapping is derived from the capability type
    # in the corresponding node template
    substitution_type_capability_type = substitution_type_capability._get_type(context)
    node_template_capability_type = node_template_capability._get_type(context)
    if not substitution_type_capability_type._is_descendant(context, node_template_capability_type):
        context.validation.report(
            u'node template capability type "{0}" is not a descendant of substitution mapping '
            u'capability "{1}" of type "{2}"'.format(
                node_template_capability_type._name,
                presentation._name,
                substitution_type_capability_type._name),
            locator=presentation._locator, level=Issue.BETWEEN_TYPES)


#
# Utils
#

def _validate_mapping_format(presentation):
    """
    Validate that the mapping is a list of 2 strings.
    """
    if not isinstance(presentation._raw, list) or \
            len(presentation._raw) != 2 or \
            not isinstance(presentation._raw[0], basestring) or \
            not isinstance(presentation._raw[1], basestring):
        return False
    return True


def _get_node_template(context, presentation):
    node_template_name = presentation._raw[0]
    node_template = context.presentation.get_from_dict('service_template', 'topology_template',
                                                       'node_templates', node_template_name)
    return node_template

def _get_input(context, our_input):
    #node_template_name = presentation._raw[0]
    inputs = context.presentation.get_from_dict('service_template', 'topology_template',
                                                       'inputs', our_input)
    return inputs

def _report_missing_node_template(context, presentation, field):
    context.validation.report(
        u'substitution mappings {field} "{node_template_mapping}" '
        u'refers to an unknown node template: {node_template_name}'.format(
            field=field,
            node_template_mapping=presentation._name,
            node_template_name=safe_repr(presentation._raw[0])),
        locator=presentation._locator, level=Issue.FIELD)


def _report_invalid_mapping_format(context, presentation, field):
    context.validation.report(
        u'substitution mapping {field} "{field_name}" is not a list of 2 strings: {value}'.format(
            field=field,
            field_name=presentation._name,
            value=safe_repr(presentation._raw)),
        locator=presentation._locator, level=Issue.FIELD)
