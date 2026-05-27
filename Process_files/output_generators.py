"""
Output Generators
Convert JSON data model to Draw.io format and HTML report
"""

import json
import re
from typing import Dict, List
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def generate_drawio(data_model: Dict) -> str:
    entities = data_model.get('dataModel', {}).get('entities', [])
    business_entities = [e for e in entities if e.get('type') == 'BusinessEntity']

    ENTITY_X = -101
    ENTITY_Y_START = 127
    ENTITY_WIDTH = 90
    ENTITY_HEIGHT = 20

    FIELD_X = -27
    FIELD_WIDTH = 166
    FIELD_HEIGHT = 20
    FIELD_Y_START = 165
    FIELD_SPACING = 28

    FIELD_GROUP_X = -29
    FIELD_GROUP_WIDTH = 158

    EXPANDED_X = 175
    EXPANDED_WIDTH = 146

    LOOKUP_ICON_SIZE = 17

    CONTAINER_X = -121
    CONTAINER_Y = 80

    COLORS = {
        'business_entity': {'fill': '#1ba1e2', 'stroke': '#006EAF', 'font': '#ffffff'},
        'general_attribute': {'fill': '#d5e8d4', 'stroke': '#82b366'},
        'identifier': {'fill': '#f8cecc', 'stroke': '#b85450'},
        'field_group': {'fill': '#e3c800', 'stroke': '#B09500', 'font': '#000000'},
        'field_group_mixed': {'fill': '#f5a623', 'stroke': '#c87f0a', 'font': '#000000'},
    }

    id_counter = [2]

    def get_next_id():
        current_id = id_counter[0]
        id_counter[0] += 1
        return str(current_id)

    def field_drawn_as_identifier_style(field):
        return field.get('isCustom', False)

    def get_field_style(field):
        if field_drawn_as_identifier_style(field):
            return COLORS['identifier']
        return COLORS['general_attribute']

    def display_field_name(field):
        name = field.get('name', 'field')
        if field.get('isCustom', False) and not re.match(r'^[xX](_|[A-Z])', str(name)):
            return f'X_{name}'
        return name

    def create_mxcell(parent, cell_id, value, style, x, y, width, height, is_vertex=True):
        cell = SubElement(parent, 'mxCell', {
            'id': cell_id,
            'parent': '1',
            'style': style,
            'value': value,
            'vertex': '1' if is_vertex else '0'
        })
        SubElement(cell, 'mxGeometry', {
            'x': str(x),
            'y': str(y),
            'width': str(width),
            'height': str(height),
            'as': 'geometry'
        })
        return cell

    def create_edge(parent, edge_id, source_id, target_id, style):
        edge = SubElement(parent, 'mxCell', {
            'id': edge_id,
            'edge': '1',
            'parent': '1',
            'source': source_id,
            'target': target_id,
            'style': style
        })
        SubElement(edge, 'mxGeometry', {'relative': '1', 'as': 'geometry'})
        return edge

    def create_lookup_icon(parent, icon_id, x, y):
        icon = SubElement(parent, 'mxCell', {
            'id': icon_id,
            'parent': '1',
            'style': 'shape=image;html=1;verticalAlign=top;verticalLabelPosition=bottom;labelBackgroundColor=#ffffff;imageAspect=0;aspect=fixed;image=https://cdn1.iconfinder.com/data/icons/material-core/10/arrow-drop-down-128.png;fillColor=#008A8A;',
            'value': '',
            'vertex': '1'
        })
        SubElement(icon, 'mxGeometry', {
            'x': str(x),
            'y': str(y),
            'width': str(LOOKUP_ICON_SIZE),
            'height': str(LOOKUP_ICON_SIZE),
            'as': 'geometry'
        })
        return icon

    # Calculate container size
    total_rows = 0
    for entity in business_entities:
        fields = entity.get('fields', [])
        field_groups_in_entity = {}
        for field in fields:
            fg = field.get('fieldGroup')
            if fg and fg != '_meta':
                field_groups_in_entity.setdefault(fg, 0)
                field_groups_in_entity[fg] += 1
            else:
                total_rows += 1
        for fg_count in field_groups_in_entity.values():
            total_rows += max(1, fg_count)

    content_bottom_y = FIELD_Y_START + (total_rows + 2) * FIELD_SPACING
    container_height = max(806, content_bottom_y - CONTAINER_Y + 50)
    container_width = max(729, EXPANDED_X + EXPANDED_WIDTH + 50 - CONTAINER_X)

    # Build XML
    mxfile = Element('mxfile', {
        'host': 'app.diagrams.net',
        'agent': 'Mozilla/5.0',
        'version': '29.3.0'
    })

    diagram = SubElement(mxfile, 'diagram', {'name': 'Data Model', 'id': 'data-model-diagram'})
    mxGraphModel = SubElement(diagram, 'mxGraphModel', {
        'dx': '1826', 'dy': '824', 'grid': '0', 'gridSize': '10',
        'guides': '1', 'tooltips': '1', 'connect': '1', 'arrows': '1',
        'fold': '1', 'page': '0', 'pageScale': '1', 'pageWidth': '850',
        'pageHeight': str(max(1100, int(container_height) + 200)),
        'math': '0', 'shadow': '0'
    })

    root = SubElement(mxGraphModel, 'root')
    SubElement(root, 'mxCell', {'id': '0'})
    SubElement(root, 'mxCell', {'id': '1', 'parent': '0'})

    # Container box
    container_id = get_next_id()
    create_mxcell(
        root, container_id, 'MDM Person Entity',
        'rounded=0;whiteSpace=wrap;html=1;horizontal=1;verticalAlign=top;align=left;fontStyle=5',
        CONTAINER_X, CONTAINER_Y, container_width, container_height
    )

    # Legend
    LABEL_PADDING = 15
    LABEL_GAP = 12
    LABEL_HEIGHT = 20
    LABEL_Y = CONTAINER_Y + LABEL_PADDING
    label_specs = [
        ('Business Entity', 97, 'business_entity'),
        ('General Attributes', 109, 'general_attribute'),
        ('Identifiers / Custom', 140, 'identifier'),
        ('Field Groups OOTB', 132, 'field_group'),
        ('Field Group Custom', 132, 'field_group_mixed'),
    ]
    legend_right = CONTAINER_X + container_width - LABEL_PADDING
    label_x = legend_right
    for text, w, key in reversed(label_specs):
        label_x -= (w + LABEL_GAP)
        c = COLORS[key]
        font_color = c.get('font', '#000000')
        style = f'rounded=0;whiteSpace=wrap;html=1;align=left;fillColor={c["fill"]};fontColor={font_color};strokeColor={c["stroke"]};'
        create_mxcell(root, get_next_id(), text, style, label_x, LABEL_Y, w, LABEL_HEIGHT)

    # Draw entities and fields
    current_field_y = FIELD_Y_START

    for entity in business_entities:
        entity_name = entity.get('name', 'Entity')
        fields = entity.get('fields', [])

        entity_id = get_next_id()
        create_mxcell(
            root, entity_id,
            f'<font color="{COLORS["business_entity"]["font"]}">{entity_name}</font>',
            f'rounded=0;whiteSpace=wrap;html=1;align=left;fillColor={COLORS["business_entity"]["fill"]};fontColor={COLORS["business_entity"]["font"]};strokeColor={COLORS["business_entity"]["stroke"]};',
            ENTITY_X, ENTITY_Y_START, ENTITY_WIDTH, ENTITY_HEIGHT
        )

        standalone_fields = []
        field_groups_dict = {}

        for field in fields:
            fg = field.get('fieldGroup')
            if fg and fg not in ('_meta', 'ROOT', 'CUSTOM'):
                field_groups_dict.setdefault(fg, []).append(field)
            else:
                standalone_fields.append(field)

        # Standalone fields
        for field in standalone_fields:
            field_name = display_field_name(field)
            field_style = get_field_style(field)
            is_lookup = field.get('isLookup', False)

            field_id = get_next_id()
            style_str = f'rounded=0;whiteSpace=wrap;html=1;align=left;fillColor={field_style["fill"]};strokeColor={field_style["stroke"]};'
            if is_lookup:
                style_str += 'spacingRight=20;'
            create_mxcell(root, field_id, field_name, style_str, FIELD_X, current_field_y, FIELD_WIDTH, FIELD_HEIGHT)

            edge_id = get_next_id()
            create_edge(root, edge_id, entity_id, field_id,
                'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;startArrow=none;startFill=0;endArrow=none;endFill=0;')

            if is_lookup:
                icon_x = FIELD_X + FIELD_WIDTH - LOOKUP_ICON_SIZE - 3
                icon_y = current_field_y + (FIELD_HEIGHT - LOOKUP_ICON_SIZE) // 2
                create_lookup_icon(root, get_next_id(), icon_x, icon_y)

            current_field_y += FIELD_SPACING

        # Field groups
        for group_name, group_fields in field_groups_dict.items():
            num_expanded = len(group_fields)
            group_y = current_field_y

            has_custom = any(field_drawn_as_identifier_style(f) for f in group_fields)
            fg_style_key = 'field_group_mixed' if has_custom else 'field_group'
            fg_c = COLORS[fg_style_key]

            group_id = get_next_id()
            create_mxcell(
                root, group_id, group_name,
                f'rounded=0;whiteSpace=wrap;html=1;fillColor={fg_c["fill"]};fontColor={fg_c["font"]};strokeColor={fg_c["stroke"]};',
                FIELD_GROUP_X, group_y, FIELD_GROUP_WIDTH, FIELD_HEIGHT
            )

            group_edge_id = get_next_id()
            create_edge(root, group_edge_id, entity_id, group_id,
                'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=0.5;exitY=1;exitDx=0;exitDy=0;entryX=0;entryY=0.5;entryDx=0;entryDy=0;startArrow=none;startFill=0;endArrow=ERmany;endFill=0;')

            expanded_y = group_y
            for group_field in group_fields:
                field_name = display_field_name(group_field)
                is_lookup = group_field.get('isLookup', False)
                gf_style = get_field_style(group_field)

                expanded_id = get_next_id()
                exp_style = f'rounded=0;whiteSpace=wrap;html=1;align=left;fillColor={gf_style["fill"]};strokeColor={gf_style["stroke"]};'
                if is_lookup:
                    exp_style += 'spacingRight=20;'
                create_mxcell(root, expanded_id, field_name, exp_style, EXPANDED_X, expanded_y, EXPANDED_WIDTH, FIELD_HEIGHT)

                exp_edge_id = get_next_id()
                create_edge(root, exp_edge_id, group_id, expanded_id,
                    'edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;entryX=0;entryY=0.5;entryDx=0;entryDy=0;startArrow=none;startFill=0;endArrow=none;endFill=0;exitX=1;exitY=0.5;exitDx=0;exitDy=0;')

                if is_lookup:
                    icon_x = EXPANDED_X + EXPANDED_WIDTH - LOOKUP_ICON_SIZE - 3
                    icon_y = expanded_y + (FIELD_HEIGHT - LOOKUP_ICON_SIZE) // 2
                    create_lookup_icon(root, get_next_id(), icon_x, icon_y)

                expanded_y += FIELD_SPACING

            current_field_y += max(1, num_expanded) * FIELD_SPACING

    xml_str = minidom.parseString(tostring(mxfile)).toprettyxml(indent='    ')
    lines = xml_str.split('\n')
    if lines[0].startswith('<?xml'):
        xml_str = '\n'.join(lines[1:])
    return xml_str.strip()


def save_drawio_file(data_model: Dict, output_path: str = "data_model.drawio"):
    xml_content = generate_drawio(data_model)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)
    print(f"Draw.io file saved to: {output_path}")
    print(f"Open this file in Draw.io (https://app.diagrams.net)")


def get_summary_stats(data_model: Dict) -> Dict:
    entities = data_model.get('dataModel', {}).get('entities', [])
    business_entities = [e for e in entities if e.get('type') == 'BusinessEntity']
    reference_entities = [e for e in entities if e.get('type') == 'ReferenceEntity']
    total_fields = sum(len(e.get('fields', [])) for e in entities)
    custom_fields = sum(
        sum(1 for f in e.get('fields', []) if f.get('isCustom', False))
        for e in entities
    )
    return {
        'total_entities': len(entities),
        'business_entities': len(business_entities),
        'reference_entities': len(reference_entities),
        'total_fields': total_fields,
        'custom_fields': custom_fields,
        'ootb_fields': total_fields - custom_fields,
        'total_relationships': len(data_model.get('dataModel', {}).get('relationships', []))
    }
