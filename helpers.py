import os # Provides functions for interacting with the operating system
import re # Provides support for regular expressions
import csv # Provides functions to work with CSV files
import xml.etree.ElementTree as ET # XML parsing library
from jinja2 import Environment, FileSystemLoader, select_autoescape # Jinja2 templating engine for HTML generation
from saxonche import PySaxonProcessor # Library for running XSLT and XPath with Saxon-EE

TEI_NS = "http://www.tei-c.org/ns/1.0" # Defines the TEI XML namespace

# --- XSLT Transformation Function ---

def transform_div_with_xslt(tei_path, edition='diplomatic', xslt_path=None):
    """
    Run Saxon XSLT to transform the TEI XML into a cleaned version (diplomatic or critical).
    Returns the transformed XML as a string.
    """
    # Determine the XSLT stylesheet file to use
    if xslt_path is None:
        xslt_filename = f"cleaning_{edition}.xsl"
    else:
        xslt_filename = xslt_path
    
    # Resolve the full path to the stylesheet
    base_dir = os.getcwd()
    xslt_path = os.path.join(base_dir, xslt_filename)
    
    # Initialize the Saxon processor
    with PySaxonProcessor(license=False) as proc:
        xslt_proc = proc.new_xslt30_processor()
        
        # Execute the transformation
        try:
            result = xslt_proc.transform_to_string(
                source_file=tei_path,
                stylesheet_file=xslt_path
            )
        except Exception as e:
            print(f"Error during XSLT transformation: {e}")
            return None

        return result
    
# --- Text Extraction and Markup Application ---

def get_text_with_markup(node):
    """
    Recursively extracts text from an XML node and applies custom, TEI-inspired markup
    to represent editorial tags like <ex>, <add>, <supplied>, <del>, <surplus>, and <gap>.
    """
    text_parts = []
    # Helper to get the local tag name without the namespace URI
    ns_tag = lambda t: t.rsplit('}', 1)[-1] if '}' in t else t

    tag = ns_tag(node.tag)

    # Apply specific markup based on the tag
    if tag == "ex": # Expansion
        inner = "".join(get_text_with_markup(c) for c in node)
        text_parts.append(f"<em>{(node.text or '')}{inner}</em>")
        if node.tail:
            text_parts.append(node.tail)
    elif tag in {"add", "supplied"}: # Addition or Supplied
        inner = "".join(get_text_with_markup(c) for c in node)
        text_parts.append(f"[{(node.text or '')}{inner}]")
        if node.tail:
            text_parts.append(node.tail)
    elif tag in {"del", "surplus"}: # Deletion or Surplus
        inner = "".join(get_text_with_markup(c) for c in node)
        text_parts.append(f"({(node.text or '')}{inner})")
        if node.tail:
            text_parts.append(node.tail)
    elif tag == "gap": # Gap in the text
        inner = "".join(get_text_with_markup(c) for c in node)
        text_parts.append(f" [...]")
        if node.tail:
            text_parts.append(node.tail)
    else: # Default behavior: just concatenate text and process children
        if node.text:
            text_parts.append(node.text)
        for c in node:
            text_parts.append(get_text_with_markup(c))
        if node.tail:
            text_parts.append(node.tail)

    return "".join(text_parts)

# --- Line Extraction and Metadata Mapping ---

def extract_lines_from_xml(xml_str, initial_folio="", initial_col=""):
    """
    Extracts each <l> (line) element from the transformed XML, processes its text,
    and maps contextual metadata (line number, grouping, folio, column, speaker) to it.
    Returns a list of dictionaries, one for each line.
    """
    import xml.etree.ElementTree as ET
    ns = {"tei": TEI_NS} # TEI namespace
    root = ET.fromstring(xml_str)
    lines = []
    line_counter = 0
    
    # Limit node list to the main <div> or the whole document
    div_elem = root.find('.//tei:div', ns)
    doc_nodes = list(div_elem.iter()) if div_elem is not None else list(root.iter())

    # Build a map of child -> parent for all nodes to traverse up the tree
    parent_map = {c: p for p in doc_nodes for c in p}

    # Tags considered as grouping containers for lines
    GROUP_TAGS = {"lg", "p", "sp"}
    ancestor_group_map = {} # Maps unique ancestor elements to a stable group ID
    next_group_id = 0

    def find_group_for_node(node):
        # Finds the nearest ancestor element that is a grouping tag (<lg>, <p>, <sp>)
        cur = node
        while cur in parent_map:
            parent = parent_map[cur]
            tag_local = parent.tag.rsplit('}', 1)[-1] if '}' in parent.tag else parent.tag
            if tag_local in GROUP_TAGS:
                return parent
            cur = parent
        return None

    # Iterate over every line (<l>) element
    for l in root.findall(".//tei:l", ns):
        line_counter += 1
        
        # Apply editorial markup to the line's text
        text = get_text_with_markup(l)
        # Normalize multiple spaces into single spaces
        text = re.sub(r"\s+", " ", text).strip()

        # Get the line's XML ID
        xml_ns = "{http://www.w3.org/XML/1998/namespace}id"
        l_id = l.get(xml_ns) or l.get("id") or ""

        # Determine the line's group ID
        ancestor = find_group_for_node(l)
        if ancestor is not None:
            if ancestor not in ancestor_group_map:
                next_group_id += 1
                ancestor_group_map[ancestor] = next_group_id
            lg_num = ancestor_group_map[ancestor]
        else:
            lg_num = 0
        lg_id = str(lg_num) if lg_num > 0 else ""

        # Find the preceding <pb> element to determine the folio number
        folio = initial_folio # Start with the folio from the source TEI
        try:
            idx = doc_nodes.index(l)
            # Scan backward through all preceding nodes for the nearest <pb>
            for prev in reversed(doc_nodes[:idx]):
                prev_tag = prev.tag.rsplit('}', 1)[-1] if '}' in prev.tag else prev.tag
                if prev_tag == 'pb':
                    folio = prev.get('n') or prev.get(xml_ns) or initial_folio
                    break
        except ValueError:
            folio = initial_folio

        # Find the preceding <cb> or <milestone> element to determine the column
        col = initial_col # Start with the column from the source TEI
        try:
            idx = doc_nodes.index(l)
            # Scan backward through all preceding nodes for the nearest column break
            for prev in reversed(doc_nodes[:idx]):
                prev_tag = prev.tag.rsplit('}', 1)[-1] if '}' in prev.tag else prev.tag
                if prev_tag == 'cb':
                    col = prev.get('n') or prev.get(xml_ns) or initial_col
                    break
                if prev_tag == 'milestone' and prev.get('unit') == 'column':
                    col = prev.get('n') or prev.get(xml_ns) or initial_col
                    break
        except ValueError:
            col = initial_col

        # Find the nearest ancestor <sp> element and extract the speaker name
        speaker = ""
        try:
            idx = doc_nodes.index(l)
            # Scan backward through all preceding nodes for the nearest <sp>
            for prev in reversed(doc_nodes[:idx]):
                prev_tag = prev.tag.rsplit('}', 1)[-1] if '}' in prev.tag else prev.tag
                if prev_tag == 'sp':
                    # Extract the speaker ID from the 'who' attribute
                    speaker = prev.attrib.get('who', '')
                    # Clean up the speaker ID
                    if speaker.startswith('#'):
                        speaker = speaker[1:]
                    break
        except (ValueError, AttributeError):
            pass

        # Append the line data to the list
        lines.append({"line_no": line_counter, "text": text, "lg": lg_id,
                      "l_id": l_id, "folio": folio, "col": col, "speaker": speaker})
    return lines

# --- Output Writing Functions ---

def write_txt(lines, outpath):
    # *** Write line data to a plain text file ***
    os.makedirs(os.path.dirname(outpath), exist_ok=True) # Ensure directory exists
    with open(outpath, "w", encoding="utf8") as fh:
        for entry in lines:
            # Remove HTML emphasis tags (<em>) before writing to TXT
            text = re.sub(r"</?em>", "", entry["text"])
            fh.write(text + "\n")

def write_csv(lines, outpath):
    # *** Write line data to a CSV file ***
    os.makedirs(os.path.dirname(outpath), exist_ok=True) # Ensure directory exists
    fieldnames = ["line_no", "text", "lg", "l_id", "folio", "col", "speaker"]
    with open(outpath, "w", newline="", encoding="utf8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in lines:
            # Remove HTML emphasis tags (<em>) before writing to CSV
            text = re.sub(r"</?em>", "", row["text"])
            writer.writerow({**row, "text": text})

def render_html(template_name, context, outpath):
    # *** Render line data into an HTML file using Jinja2 ***
    os.makedirs(os.path.dirname(outpath), exist_ok=True) # Ensure directory exists
    tmpl_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(tmpl_dir), autoescape=select_autoescape(['html']))
    tmpl = env.get_template(template_name)
    html = tmpl.render(**context) # Render the template with the provided data
    with open(outpath, "w", encoding="utf8") as fh:
        fh.write(html)

# --- Main Processing Function ---

def process_div(tei_path, out_root="out", div_id=None, initial_folio="", initial_col="", manifest_url="", metadata_dict=None):
    """
    Orchestrates the transformation, extraction, and output of TEI XML for a single div.
    Generates TXT, CSV, and HTML for both 'diplomatic' and 'critical' editions.
    """
    # Use provided ID or the filename as the base name
    if div_id:
        tei_basename = div_id
    else:
        tei_basename = os.path.splitext(os.path.basename(tei_path))[0]
    
    # 1. Extract details from the metadata
    div_state = metadata_dict.get(tei_basename, {}).get('state', 'incomplete').lower()
    norm_div_state = div_state.replace(' ', '-') # Normalized state for directory names
    title = metadata_dict.get(tei_basename, {}).get('title', tei_basename)
    notes = metadata_dict.get(tei_basename, {}).get('notes', '')
    
    # Base paths for output types
    out_txt = os.path.join(out_root, "txt")
    out_csv = os.path.join(out_root, "csv")
    out_html = os.path.join(out_root, "html")

    # 2. Create the full state-sorted base directories
    state_txt_dir = os.path.join(out_txt, norm_div_state)
    state_csv_dir = os.path.join(out_csv, norm_div_state)

    # 3. Create edition-specific subfolders (e.g., out/txt/complete/diplomatic)
    for d in [state_txt_dir, state_csv_dir]:
        os.makedirs(os.path.join(d, "diplomatic"), exist_ok=True)
        os.makedirs(os.path.join(d, "critical"), exist_ok=True)
    
    os.makedirs(out_html, exist_ok=True) # Ensure base HTML folder exists

    filename_base = tei_basename.lower()

    # Build folio -> canvas mapping from the TEI file (for IIIF image links)
    folio_to_canvas = {}
    try:
        tei_root = ET.parse(tei_path).getroot()
        ns = {"tei": TEI_NS}
        for pb in tei_root.findall(".//tei:pb", ns): # Find all page break elements
            pb_n = pb.get("n") or pb.get("{http://www.w3.org/XML/1998/namespace}id") or ""
            pb_facs = pb.get("facs") or "" # IIIF canvas ID
            if pb_n and pb_facs:
                folio_to_canvas[pb_n] = pb_facs
    except Exception:
        pass

    # 4. Define the allowed states for HTML generation
    ALLOWED_HTML_STATES = ['complete', 'near-complete']
    generate_html = norm_div_state in ALLOWED_HTML_STATES

    # Process both diplomatic and critical editions
    for edition in ("diplomatic", "critical"):
        transformed_xml = transform_div_with_xslt(tei_path, edition=edition) # Run XSLT
        lines = extract_lines_from_xml(transformed_xml, initial_folio=initial_folio, initial_col=initial_col) # Extract line data

        # 5. Build state-sorted paths for TXT and CSV
        txt_out = os.path.join(state_txt_dir, edition, f"{tei_basename}.txt")
        csv_out = os.path.join(state_csv_dir, edition, f"{tei_basename}.csv")
        html_out = os.path.join(out_html, f"{filename_base}-{edition}.html")

        write_txt(lines, txt_out) # Write TXT
        write_csv(lines, csv_out) # Write CSV
        print(f"Wrote {edition} TXT/CSV (state: {norm_div_state}): TXT->{txt_out}, CSV->{csv_out}")

        # 6. Conditional HTML generation
        if generate_html:
            # Determine the starting canvas URL for image display
            canvas_url = None
            if lines and len(lines) > 0:
                first_folio = lines[0].get("folio")
                if first_folio and first_folio in folio_to_canvas:
                    canvas_url = folio_to_canvas[first_folio]

            # Determine text and link for the switch button (diplomatic <-> critical)
            if edition == "critical":
                other_version_url = tei_basename.lower() + "-diplomatic.html"
                other_version_label = "Go to diplomatic"
            else:
                other_version_url = tei_basename.lower() + "-critical.html"
                other_version_label = "Go to critical"

            # Context dictionary passed to the HTML template
            context = {
                "project_title": "The Texts of BnF fr. 24432",
                "project_subtitle": "A cumulative, work-in-progress digital edition by Sebastian Dows-Miller",
                "div_id": tei_basename,
                "title": title,
                "edition": edition,
                "lines": lines,
                "manifest_url": manifest_url,
                "canvas_url": canvas_url,
                "initial_folio": initial_folio or "",
                "folio_to_canvas": folio_to_canvas,
                "facs": None,
                "other_version_url": other_version_url,
                "other_version_label": other_version_label,
                "state": div_state,
                "notes": notes
            }
            render_html("page_template.html", context, html_out) # Render and write HTML
            print(f"Wrote {edition} HTML: HTML->{html_out}")
        else:
            print(f"Skipped {edition} HTML generation (state: {norm_div_state}).")

# --- Helper Functions (From original `helpers.py` or defined here) ---

def load_metadata(meta_file_path):
    """
    Loads all data from the specified CSV file, using the 'id' column as the key.
    Returns: dict: A dictionary where key is the 'id' (xml:id) and value is the 
              full row data (as a dictionary).
    """
    metadata = {}
    try:
        # Use 'utf-8-sig' to handle Byte Order Marks (BOMs) common in Excel CSVs
        with open(meta_file_path, mode='r', encoding='utf-8-sig') as file:
            reader = csv.DictReader(file)
            
            # Normalize and check the column names (fields)
            fieldnames = [name.strip() for name in reader.fieldnames]
            reader.fieldnames = fieldnames
            
            if 'id' not in fieldnames:
                print(f"Error: CSV header 'id' not found. Found headers: {', '.join(fieldnames)}")
                sys.exit(1)

            for i, row in enumerate(reader, 1):
                # Ensure the 'id' value exists
                if row.get('id', '').strip():
                    div_id = row['id'].strip()
                    row['state'] = row.get('state', 'incomplete').strip().lower() 
                    metadata[div_id] = row
                else:
                    print(f"Warning: Skipping row {i} because 'id' column is empty.")
                    
    except FileNotFoundError:
        print(f"Error: Metadata file not found at {meta_file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading metadata file: {e}")
        sys.exit(1)
        
    return metadata

def get_folio_and_col_at_div(div_node_xml, source_root):
    """
    Finds the nearest preceding <pb> (page break) and <cb> (column break) or <milestone> 
    elements before the div in the source document to determine the initial folio and column. 
    Returns (folio, col) strings.
    """
    TEI_NS = "{http://www.tei-c.org/ns/1.0}"
    XML_ID_NS = "{http://www.w3.org/XML/1998/namespace}id"
    
    # Extract xml:id from div_xml
    m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_node_xml)
    if not m:
        return "", ""
    
    div_id = m.group(1)
    
    # Find the div element in the source XML
    div_elem_in_source = None
    for elem in source_root.iter():
        if elem.tag == f"{TEI_NS}div" and elem.get(XML_ID_NS) == div_id:
            div_elem_in_source = elem
            break
    
    if div_elem_in_source is None:
        return "", ""
    
    # Get a list of all nodes and find the div's position
    all_nodes = list(source_root.iter())
    try:
        div_idx = all_nodes.index(div_elem_in_source)
    except ValueError:
        return "", ""
    
    # Scan backwards for the nearest <pb> and column break
    folio = ""
    col = ""
    for prev_node in reversed(all_nodes[:div_idx]):
        if prev_node.tag == f"{TEI_NS}pb" and not folio:
            folio = prev_node.get('n') or prev_node.get(XML_ID_NS) or ""
        if not col:
            if prev_node.tag == f"{TEI_NS}cb":
                col = prev_node.get('n') or prev_node.get(XML_ID_NS) or ""
            elif prev_node.tag == f"{TEI_NS}milestone" and prev_node.get('unit') == 'column':
                col = prev_node.get('n') or prev_node.get(XML_ID_NS) or ""
        if folio and col:
            break
    
    return folio, col


def get_preceding_pb_element(div_node_xml, source_root):
    """
    Finds and returns the nearest preceding <pb> element before the div in the source document.
    """
    TEI_NS = "{http://www.tei-c.org/ns/1.0}"
    XML_ID_NS = "{http://www.w3.org/XML/1998/namespace}id"
    
    # Extract xml:id from div_xml
    m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_node_xml)
    if not m:
        return None
    
    div_id = m.group(1)
    
    # Find the div element in the source XML
    div_elem_in_source = None
    for elem in source_root.iter():
        if elem.tag == f"{TEI_NS}div" and elem.get(XML_ID_NS) == div_id:
            div_elem_in_source = elem
            break
    
    if div_elem_in_source is None:
        return None
    
    # Get a list of all nodes and find the div's position
    all_nodes = list(source_root.iter())
    try:
        div_idx = all_nodes.index(div_elem_in_source)
    except ValueError:
        return None
    
    # Scan backwards for the nearest <pb>
    for prev_node in reversed(all_nodes[:div_idx]):
        if prev_node.tag == f"{TEI_NS}pb":
            return prev_node
    
    return None

def simple_folio_sort_key(fol_range):
    """
    Extracts the first sequence of numbers from a folio reference for numerical sorting.
    Returns: int: The integer value of the first number found, or a large number if none is found.
    """
    if not fol_range:
        return 999999

    # Regex to capture the first sequence of one or more digits
    match = re.match(r'(\d+)', fol_range)
    if match:
        return int(match.group(1))
    
    # Fallback for non-standard references
    return 999999