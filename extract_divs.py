"""
Main driver:
- Load TEI XML from xml/
- Find all <div> elements with @subtype="transcription-complete"
- For each, write minimal TEI file and call processing functions to create outputs
- Extract folio/column info from the source to pass through to process_div
"""

import os
import sys
import re
import xml.etree.ElementTree as ET
from saxonche import PySaxonProcessor
from jinja2 import Environment, FileSystemLoader
from process_div import process_div

INPUT_DIR = "xml"
INPUT_FILE = os.path.join(INPUT_DIR, "fr24432.xml")
OUT_ROOT = "out"
OUT_TEI_DIR = os.path.join(OUT_ROOT, "tei")
os.makedirs(OUT_TEI_DIR, exist_ok=True)

def get_folio_and_col_at_div(div_node_xml, source_root):
    """
    Given a div node XML (as string) and the full source XML root (ElementTree),
    find the nearest preceding <pb> and <cb> or <milestone unit="column"> elements
    before the div in the source document. Return (folio, col) strings.
    """
    TEI_NS = "{http://www.tei-c.org/ns/1.0}"
    
    # Try to extract xml:id from div_xml to find the div in the source
    m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_node_xml)
    if not m:
        return "", ""
    
    div_id = m.group(1)
    
    # Find the div in the source XML
    div_elem_in_source = None
    for elem in source_root.iter():
        if elem.tag == f"{TEI_NS}div":
            xml_id_attr = elem.get(f"{{http://www.w3.org/XML/1998/namespace}}id")
            if xml_id_attr == div_id:
                div_elem_in_source = elem
                break
    
    if div_elem_in_source is None:
        return "", ""
    
    # Build full document node list and find index of div
    all_nodes = list(source_root.iter())
    try:
        div_idx = all_nodes.index(div_elem_in_source)
    except ValueError:
        return "", ""
    
    # Scan backwards from div position for <pb> and <cb> / milestone
    folio = ""
    col = ""
    for prev_node in reversed(all_nodes[:div_idx]):
        if prev_node.tag == f"{TEI_NS}pb" and not folio:
            folio = prev_node.get('n') or prev_node.get(f"{{http://www.w3.org/XML/1998/namespace}}id") or ""
        if not col:
            if prev_node.tag == f"{TEI_NS}cb":
                col = prev_node.get('n') or prev_node.get(f"{{http://www.w3.org/XML/1998/namespace}}id") or ""
            elif prev_node.tag == f"{TEI_NS}milestone" and prev_node.get('unit') == 'column':
                col = prev_node.get('n') or prev_node.get(f"{{http://www.w3.org/XML/1998/namespace}}id") or ""
        if folio and col:
            break
    
    return folio, col


def get_preceding_pb_element(div_node_xml, source_root):
    """
    Given a div node XML (as string) and the full source XML root (ElementTree),
    find the nearest preceding <pb> element before the div in the source document.
    Return the pb element as an ElementTree Element or None.
    """
    TEI_NS = "{http://www.tei-c.org/ns/1.0}"
    
    # Extract xml:id from div_xml to find the div in the source
    m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_node_xml)
    if not m:
        return None
    
    div_id = m.group(1)
    
    # Find the div in the source XML
    div_elem_in_source = None
    for elem in source_root.iter():
        if elem.tag == f"{TEI_NS}div":
            xml_id_attr = elem.get(f"{{http://www.w3.org/XML/1998/namespace}}id")
            if xml_id_attr == div_id:
                div_elem_in_source = elem
                break
    
    if div_elem_in_source is None:
        return None
    
    # Build full document node list and find index of div
    all_nodes = list(source_root.iter())
    try:
        div_idx = all_nodes.index(div_elem_in_source)
    except ValueError:
        return None
    
    # Scan backwards from div position for <pb>
    for prev_node in reversed(all_nodes[:div_idx]):
        if prev_node.tag == f"{TEI_NS}pb":
            return prev_node
    
    return None


with PySaxonProcessor(license=False) as proc:
    builder = proc.new_document_builder()
    try:  
        doc = builder.parse_xml(xml_file_name=INPUT_FILE)  
    except Exception as e:  
        print("Error loading TEI XML:", e)  
        sys.exit(1)  

    xp = proc.new_xpath_processor()  
    xp.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")  
    xp.set_context(xdm_item=doc)  

    # Get all divs with subtype="transcription-complete"
    divs = xp.evaluate('.//tei:div[@subtype="transcription-complete"]')  

    if not divs:  
        print("No transcription-complete divs found.")  
        sys.exit(1)  

    # Ensure we have a list-like object
    if hasattr(divs, "size"):  
        num_divs = divs.size  
    else:  
        divs = [divs]  
        num_divs = 1  

    print(f"Found {num_divs} transcription-complete div(s).")  

    # Extract teiHeader if present
    hdr_nodes = xp.evaluate('.//tei:teiHeader')  
    tei_header_xml = hdr_nodes.item_at(0).to_string() if hasattr(hdr_nodes, "size") and hdr_nodes.size > 0 else ""  

    # Extract IIIF manifest URL from teiHeader
    manifest_url = ""
    try:
        xp_manifest = proc.new_xpath_processor()
        xp_manifest.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
        xp_manifest.set_context(xdm_item=doc)
        # Look for bibl element with @subtype="full" and @type="iiif-manifest", then get the ref/@target
        manifest_nodes = xp_manifest.evaluate('.//tei:bibl[@subtype="full"][@type="iiif-manifest"]/tei:ref/@target/string()')
        if hasattr(manifest_nodes, "size") and manifest_nodes.size > 0:
            manifest_url = manifest_nodes.item_at(0).to_string() if hasattr(manifest_nodes.item_at(0), "to_string") else str(manifest_nodes.item_at(0))
    except Exception:
        pass

    # Load source XML with ElementTree to extract folio/col info
    source_root = ET.parse(INPUT_FILE).getroot()

    for i, div_node in enumerate(divs if isinstance(divs, list) else [divs.item_at(j) for j in range(divs.size)]):  
        div_xml = div_node.to_string()  

        # Extract xml:id (try XPath first, fall back to regex on serialized node)
        try:
            xp_id = proc.new_xpath_processor()
            xp_id.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
            xp_id.set_context(xdm_item=div_node)
            id_value = xp_id.evaluate('string(@xml:id)')
            if hasattr(id_value, "string_value") and id_value.string_value:
                div_id = id_value.string_value
            elif hasattr(id_value, "value") and id_value.value:
                div_id = id_value.value
            else:
                m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_xml)
                div_id = m.group(1) if m else f"div_{i+1}"
        except Exception:
            m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_xml)
            div_id = m.group(1) if m else f"div_{i+1}"

        # Extract folio and column info from source TEI
        initial_folio, initial_col = get_folio_and_col_at_div(div_xml, source_root)

        # Get the preceding pb element and serialize it
        preceding_pb_elem = get_preceding_pb_element(div_xml, source_root)
        preceding_pb_xml = ""
        if preceding_pb_elem is not None:
            preceding_pb_xml = ET.tostring(preceding_pb_elem, encoding="unicode")

        # Create minimal TEI wrapper
        body_content = preceding_pb_xml + div_xml if preceding_pb_xml else div_xml
        tei_out = "\n".join([  
            '<TEI xmlns="http://www.tei-c.org/ns/1.0">',  
            tei_header_xml,  
            "<text><body>",  
            body_content,  
            "</body></text>",  
            "</TEI>",  
        ])  

        # Write minimal TEI file
        out_path = os.path.join(OUT_TEI_DIR, f"{div_id}.xml")  
        with open(out_path, "w", encoding="utf-8") as fh:  
            fh.write(tei_out)  

        print(f"Wrote TEI for {div_id} -> {out_path}")  

        # Process diplomatic/critical editions, passing folio/col metadata and manifest URL
        process_div(out_path, out_root=OUT_ROOT, div_id=div_id, initial_folio=initial_folio, initial_col=initial_col, manifest_url=manifest_url)
# Build index afterwards
env = Environment(loader=FileSystemLoader("templates"))
index_tmpl = env.get_template("index_template.html")

listing = []
for fname in sorted(os.listdir(OUT_TEI_DIR)):
    if fname.endswith(".xml"):
        base = fname[:-4]
        base_lower = base.lower()
        listing.append({
            "id": base,
            "tei": f"../tei/{fname}",
            "diplomatic_html": f"{base_lower}-diplomatic.html",
            "critical_html": f"{base_lower}-critical.html",
        })

index_html = index_tmpl.render(listing=listing, project_title="My TEI Project")
index_out = os.path.join(OUT_ROOT, "html", "index.html")

with open(index_out, "w", encoding="utf8") as fh:
    fh.write(index_html)

print(f"Wrote index -> {index_out}")
