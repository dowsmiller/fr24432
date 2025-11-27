import os
import re
import csv
import xml.etree.ElementTree as ET
from jinja2 import Environment, FileSystemLoader, select_autoescape
from saxonche import PySaxonProcessor

TEI_NS = "http://www.tei-c.org/ns/1.0"

# ------------------ CLEANING STRATEGIES via XSLT ------------------ #
def transform_div_with_xslt(tei_path, edition='diplomatic', xslt_path=None):
    """
    Run Saxon/C XSLT to produce transformed XML (diplomatic or critical).
    Returns XML string.
    """
    # Resolve stylesheet path based on edition if not provided
    if xslt_path is None:
        xslt_filename = f"cleaning_{edition}.xsl"
    else:
        xslt_filename = xslt_path
    
    # Resolve stylesheet path to absolute
    base_dir = os.getcwd()
    xslt_path = os.path.join(base_dir, xslt_filename)
    
    with PySaxonProcessor(license=False) as proc:
        xslt_proc = proc.new_xslt30_processor()
        
        # Transform using source and stylesheet files
        try:
            result = xslt_proc.transform_to_string(
                source_file=tei_path,
                stylesheet_file=xslt_path
            )
        except Exception as e:
            print(f"Error during XSLT transformation: {e}")
            return None

        return result

def extract_lines_from_xml(xml_str, initial_folio="", initial_col=""):
    """
    Minimal extraction: find <l> elements, concatenate text, normalize whitespace.
    initial_folio and initial_col provide the folio/column state at the start of
    the div (extracted from the source TEI in extract_divs.py).
    Returns list of dicts.
    """
    import xml.etree.ElementTree as ET
    ns = {"tei": TEI_NS}
    root = ET.fromstring(xml_str)
    lines = []
    line_counter = 0
    
    # Locate the main <div> (we process one div per file). Limit traversal to
    # the nodes inside that div so numbering restarts for each div.
    div_elem = root.find('.//tei:div', ns)
    if div_elem is None:
        doc_nodes = list(root.iter())
    else:
        doc_nodes = list(div_elem.iter())

    # Build a parent map for nodes under the div
    parent_map = {c: p for p in doc_nodes for c in p}

    # Group lines by their nearest ancestor group container. Look for
    # <lg>, <p>, or <sp> as grouping containers and assign a stable group id
    # based on the ancestor element. This is robust even when the XSLT
    # flattens/changes traversal order.
    GROUP_TAGS = {"lg", "p", "sp"}
    # parent_map maps child -> parent for nodes under the div
    ancestor_group_map = {}
    next_group_id = 0

    def find_group_for_node(node):
        # Walk up using parent_map until we find an ancestor in GROUP_TAGS
        cur = node
        while cur in parent_map:
            parent = parent_map[cur]
            tag_local = parent.tag.rsplit('}', 1)[-1] if '}' in parent.tag else parent.tag
            if tag_local in GROUP_TAGS:
                return parent
            cur = parent
        return None

    for l in root.findall(".//tei:l", ns):
        line_counter += 1
        # Concatenate all text nodes within the <l> element
        text = "".join(l.itertext())
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()
        # Remove unwanted spaces around apostrophes (both typographic ’ and ASCII ')
        text = re.sub(r"\s*’\s*", "’", text)
        text = re.sub(r"\s*'\s*", "'", text)

        # l_id: xml:id is in the XML namespace
        xml_ns = "{http://www.w3.org/XML/1998/namespace}id"
        l_id = l.get(xml_ns) or l.get("id") or ""

        # lg: determine the nearest grouping ancestor (<lg>, <p>, <sp>) and
        # assign a stable numeric group id per ancestor element
        ancestor = find_group_for_node(l)
        if ancestor is not None:
            if ancestor not in ancestor_group_map:
                next_group_id += 1
                ancestor_group_map[ancestor] = next_group_id
            lg_num = ancestor_group_map[ancestor]
        else:
            lg_num = 0
        lg_id = str(lg_num) if lg_num > 0 else ""

        # folio: use initial_folio (from source), then update if a new <pb> is found
        # within this div's transformed XML
        folio = initial_folio
        try:
            idx = doc_nodes.index(l)
            for prev in reversed(doc_nodes[:idx]):
                prev_tag = prev.tag.rsplit('}', 1)[-1] if '}' in prev.tag else prev.tag
                if prev_tag == 'pb':
                    folio = prev.get('n') or prev.get(xml_ns) or initial_folio
                    break
        except ValueError:
            folio = initial_folio

        # col: use initial_col (from source), then update if a new <cb> or milestone
        # is found within this div's transformed XML
        col = initial_col
        try:
            idx = doc_nodes.index(l)
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

        # speaker: find the nearest ancestor <sp> element and extract speaker name
        speaker = ""
        try:
            idx = doc_nodes.index(l)
            for prev in reversed(doc_nodes[:idx]):
                prev_tag = prev.tag.rsplit('}', 1)[-1] if '}' in prev.tag else prev.tag
                if prev_tag == 'sp':
                    # Found the enclosing <sp>, now find its <speaker> child
                    speaker_elem = prev.find('tei:speaker', ns)
                    if speaker_elem is not None:
                        speaker = "".join(speaker_elem.itertext()).strip()
                    break
        except (ValueError, AttributeError):
            pass

        lines.append({"line_no": line_counter, "text": text, "lg": lg_id,
                      "l_id": l_id, "folio": folio, "col": col, "speaker": speaker})
    return lines

# ------------------ OUTPUT WRITING (unchanged) ------------------ #

def write_txt(lines, outpath):
    with open(outpath, "w", encoding="utf8") as fh:
        for entry in lines:
            fh.write(entry["text"] + "\n")

def write_csv(lines, outpath):
    fieldnames = ["line_no", "text", "lg", "l_id", "folio", "col", "speaker"]
    with open(outpath, "w", newline="", encoding="utf8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in lines:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

def render_html(template_name, context, outpath):
    tmpl_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(loader=FileSystemLoader(tmpl_dir), autoescape=select_autoescape(['html']))
    tmpl = env.get_template(template_name)
    html = tmpl.render(**context)
    with open(outpath, "w", encoding="utf8") as fh:
        fh.write(html)

# ------------------ PUBLIC FUNCTION ------------------ #

def process_div(tei_path, out_root="out", div_id=None, initial_folio="", initial_col="", manifest_url=""):
    # Use provided div_id (from @xml:id) when available, otherwise fall back
    # to the TEI filename basename.
    if div_id:
        tei_basename = div_id
    else:
        tei_basename = os.path.splitext(os.path.basename(tei_path))[0]
    out_txt = os.path.join(out_root, "txt")
    out_csv = os.path.join(out_root, "csv")
    out_html = os.path.join(out_root, "html")

    for d in [out_txt, out_csv]:
        os.makedirs(os.path.join(d, "diplomatic"), exist_ok=True)
        os.makedirs(os.path.join(d, "critical"), exist_ok=True)
    os.makedirs(out_html, exist_ok=True)

    # Convert div_id to lowercase for filenames
    filename_base = tei_basename.lower()

    # Extract folio -> canvas mapping from the extracted TEI file (now includes preceding pb)
    # Look for pb elements with @facs attributes and build a mapping
    folio_to_canvas = {}
    try:
        tei_root = ET.parse(tei_path).getroot()
        ns = {"tei": TEI_NS}
        for pb in tei_root.findall(".//tei:pb", ns):
            pb_n = pb.get("n") or pb.get("{http://www.w3.org/XML/1998/namespace}id") or ""
            pb_facs = pb.get("facs") or ""
            if pb_n and pb_facs:
                folio_to_canvas[pb_n] = pb_facs
    except Exception:
        pass

    for edition in ("diplomatic", "critical"):
        transformed_xml = transform_div_with_xslt(tei_path, edition=edition)
        lines = extract_lines_from_xml(transformed_xml, initial_folio=initial_folio, initial_col=initial_col)

        txt_out = os.path.join(out_txt, edition, f"{tei_basename}.txt")
        csv_out = os.path.join(out_csv, edition, f"{tei_basename}.csv")
        html_out = os.path.join(out_html, f"{filename_base}-{edition}.html")

        write_txt(lines, txt_out)
        write_csv(lines, csv_out)

        # Determine canvas_url from first folio in lines
        canvas_url = None
        first_folio = None
        if lines and len(lines) > 0:
            first_folio = lines[0].get("folio")
            if first_folio and first_folio in folio_to_canvas:
                canvas_url = folio_to_canvas[first_folio]

        context = {
            "project_title": "The texts of BnF fr. 24432",
            "project_subtitle": "A cumulative, work-in-progress digital edition",
            "div_id": tei_basename,
            "edition": edition,
            "lines": lines,
            "manifest_url": manifest_url,
            "canvas_url": canvas_url,
            "initial_folio": initial_folio or "",
            "folio_to_canvas": folio_to_canvas,
            "facs": None,
            "notes": "Replace with project-specific metadata"
        }
        render_html("page_template.html", context, html_out)
        print(f"Wrote {edition} outputs: TXT->{txt_out}, CSV->{csv_out}, HTML->{html_out}")

