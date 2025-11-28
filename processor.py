import os # Provides functions for interacting with the operating system
import sys # Provides access to system-specific parameters and functions
import re # Provides support for regular expressions
import csv # Provides functions to work with CSV files
import xml.etree.ElementTree as ET # XML parsing library
from saxonche import PySaxonProcessor # Library for running XSLT and XPath with Saxon-EE
from jinja2 import Environment, FileSystemLoader # Jinja2 templating engine for HTML generation
from helpers import process_div, get_folio_and_col_at_div, get_preceding_pb_element, simple_folio_sort_key, load_metadata # Custom helper functions

# --- Configuration ---

INPUT_DIR = "in" # Directory for input files
INPUT_FILE = os.path.join(INPUT_DIR, "fr24432.xml") # Path to the main input XML file
META_FILE = os.path.join(INPUT_DIR, "meta.csv") # Path to the metadata CSV file
OUT_ROOT = "out" # Root directory for all output
OUT_TEI_DIR = os.path.join(OUT_ROOT, "tei") # Output directory for extracted TEI XML files
os.makedirs(OUT_TEI_DIR, exist_ok=True) # Create the TEI output directory if it doesn't exist

# --- Data Loading and Validation ---

# 1. Load the target metadata from the CSV file
metadata_dict = load_metadata(META_FILE) # Load metadata into a dictionary
target_ids = metadata_dict.keys() # Get a list of XML IDs to process

# Exit if no IDs are found in the metadata
if not target_ids:
    print("No IDs found in the metadata file. Exiting.")
    sys.exit(1)

# Format the IDs into a comma-separated string for use in an XPath expression
target_ids_xpath = ", ".join(f"'{id_}'" for id_ in target_ids)

# Construct the XPath expression to select the desired 'div' elements
XPATH_EXPRESSION = f'.//tei:div[string(@xml:id) = ({target_ids_xpath})]'

# --- Saxon Processor and XML Parsing ---

# Initialize the Saxon processor
with PySaxonProcessor(license=False) as proc:
    builder = proc.new_document_builder()
    try:  
        doc = builder.parse_xml(xml_file_name=INPUT_FILE) # Parse the main XML document 
    except Exception as e:  
        print("Error loading TEI XML:", e)  
        sys.exit(1)  

    xp = proc.new_xpath_processor() # Create a new XPath processor 
    xp.declare_namespace("tei", "http://www.tei-c.org/ns/1.0") # Declare TEI namespace
    xp.set_context(xdm_item=doc) # Set the XML document as the context

    # 2. Get all divs with xml:id matching the list from the CSV
    print(f"Searching for {len(target_ids)} divs...")
    divs = xp.evaluate(XPATH_EXPRESSION) # Execute the XPath expression

    # Exit if no matching divs are found
    if not divs:  
        print(f"No divs found matching the {len(target_ids)} IDs in the XML.")  
        sys.exit(1)  

    # Normalize the result into a list and get the count
    if hasattr(divs, "size"):  
        num_divs = divs.size  
    else:  
        divs = [divs]  
        num_divs = 1  

    print(f"Found {num_divs} matching div(s).")  

    # Extract teiHeader if present
    hdr_nodes = xp.evaluate('.//tei:teiHeader') # Find the TEI header element
    tei_header_xml = hdr_nodes.item_at(0).to_string() if hasattr(hdr_nodes, "size") and hdr_nodes.size > 0 else ""  # Get the header XML string

    # Extract IIIF manifest URL from teiHeader
    manifest_url = "" # Initialize manifest URL
    try:
        xp_manifest = proc.new_xpath_processor() # New XPath processor for manifest URL
        xp_manifest.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
        xp_manifest.set_context(xdm_item=doc)
        # XPath to find the manifest URL
        manifest_nodes = xp_manifest.evaluate('.//tei:bibl[@subtype="full"][@type="iiif-manifest"]/tei:ref/@target/string()')
        if hasattr(manifest_nodes, "size") and manifest_nodes.size > 0:
            # Extract and store the URL string
            manifest_url = manifest_nodes.item_at(0).to_string() if hasattr(manifest_nodes.item_at(0), "to_string") else str(manifest_nodes.item_at(0))
    except Exception:
        pass # Ignore errors during manifest extraction

    # Load source XML (using ET for helpers) and XSLT processor
    source_root = ET.parse(INPUT_FILE).getroot() # Parse the XML again with ElementTree for helper functions
    xslt30 = proc.new_xslt30_processor() # Create XSLT processor
    executable = xslt30.compile_stylesheet(stylesheet_file="extract_div.xsl") # Compile the XSLT stylesheet

    # --- Process Each Target Div ---

    # Iterate over all matching div nodes
    for i, div_node in enumerate(divs if isinstance(divs, list) else [divs.item_at(j) for j in range(divs.size)]):  
        div_xml = div_node.to_string()  # Get the XML string for the current div

        # Extract xml:id
        try:
            xp_id = proc.new_xpath_processor() # New XPath processor for ID
            xp_id.declare_namespace("tei", "http://www.tei-c.org/ns/1.0")
            xp_id.set_context(xdm_item=div_node)
            id_value = xp_id.evaluate('string(@xml:id)') # Get the xml:id attribute value
            
            # Extract the ID value
            if hasattr(id_value, "string_value") and id_value.string_value:
                div_id = id_value.string_value
            elif hasattr(id_value, "value") and id_value.value:
                div_id = id_value.value
            else:
                m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_xml) # Fallback using regex
                div_id = m.group(1) if m else f"div_{i+1}"
        except Exception:
            m = re.search(r'xml:id\s*=\s*"([^"]+)"', div_xml) # Fallback using regex
            div_id = m.group(1) if m else f"div_{i+1}"

        # Get metadata for the current div
        current_div_metadata = metadata_dict.get(div_id, {})
        div_state = current_div_metadata.get('state', 'incomplete').lower() # Get the 'state' (e.g., complete, incomplete)
        norm_div_state = div_state.replace(' ', '-') # Normalize state for directory name

        # Extract folio and column info using helper function
        initial_folio, initial_col = get_folio_and_col_at_div(div_xml, source_root)

        # Get the preceding <pb> element using helper function
        preceding_pb_elem = get_preceding_pb_element(div_xml, source_root)
        preceding_pb_xml = ""
        if preceding_pb_elem is not None:
            preceding_pb_xml = ET.tostring(preceding_pb_elem, encoding="unicode") # Serialize the preceding <pb>

        # Set the 'div-id' parameter for the XSLT transformation
        xdm_div_id = proc.make_string_value(div_id)
        executable.set_parameter("div-id", xdm_div_id)

        # Perform the XSLT transformation
        result = executable.transform_to_string(
            xdm_node=doc
        )

        # Define output path based on the state
        state_tei_dir = os.path.join(OUT_TEI_DIR, norm_div_state)
        os.makedirs(state_tei_dir, exist_ok=True) # Create state directory
        
        out_path = os.path.join(state_tei_dir, f"{div_id}.xml")
        
        # Write the transformed TEI XML to a file
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(result)

        print(f"Wrote TEI for {div_id} -> {out_path}")
 
        # Process the extracted TEI (generate HTML, CSV, TXT) using helper function
        process_div(out_path, out_root=OUT_ROOT, div_id=div_id, initial_folio=initial_folio, initial_col=initial_col, manifest_url=manifest_url, metadata_dict=metadata_dict)
        
# --- Generate Index HTML ---

# Define which states are allowed to have HTML links
ALLOWED_HTML_STATES = ['complete', 'near-complete']
env = Environment(loader=FileSystemLoader("templates")) # Setup Jinja2 environment
index_tmpl = env.get_template("index_template.html") # Load the index template

# Initialize dictionary to group items by their state
grouped_listing = {'complete': [], 'near-complete': [], 'incomplete': []}

# Iterate through the generated TEI output directories
for state_dir in os.listdir(OUT_TEI_DIR):
    state_path = os.path.join(OUT_TEI_DIR, state_dir)
    if os.path.isdir(state_path):
        for fname in sorted(os.listdir(state_path)):
            if fname.endswith(".xml"):
                base = fname[:-4] # Get the base filename (the ID)
                # Get relevant metadata for the index list
                div_state = metadata_dict.get(base, {}).get('state', 'incomplete').lower()
                norm_div_state = div_state.replace(' ', '-')
                title = metadata_dict.get(base, {}).get('title', base)
                summary = metadata_dict.get(base, {}).get('summary', '')
                fol_range = metadata_dict.get(base, {}).get('fol_range', '')
                edition_uri = metadata_dict.get(base, {}).get('edition_uri', '')
                edition_title = metadata_dict.get(base, {}).get('edition_title', '')
                arlima_uri = metadata_dict.get(base, {}).get('arlima_uri', '')
                notes = metadata_dict.get(base, {}).get('notes', '')

                # Determine if HTML links should be included based on state
                include_html = div_state in ALLOWED_HTML_STATES
                base_lower = base.lower()
                
                # Set HTML paths conditionally
                diplomatic_html_path = f"{base_lower}-diplomatic.html" if include_html else ""
                critical_html_path = f"{base_lower}-critical.html" if include_html else ""

                # Create a dictionary for the current item
                item = {
                    "id": base,
                    "tei": f"../tei/{norm_div_state}/{fname}", # Path to TEI XML
                    "diplomatic_html": diplomatic_html_path, # Path to diplomatic HTML
                    "critical_html": critical_html_path, # Path to critical HTML
                    # Paths to other formats (CSV, TXT)
                    "diplomatic_csv": f"../csv/{norm_div_state}/diplomatic/{fname[:-4]}.csv",
                    "critical_csv": f"../csv/{norm_div_state}/critical/{fname[:-4]}.csv",
                    "diplomatic_txt": f"../txt/{norm_div_state}/diplomatic/{fname[:-4]}.txt",
                    "critical_txt": f"../txt/{norm_div_state}/critical/{fname[:-4]}.txt",
                    "title": title,
                    "summary": summary,
                    "fol_range": fol_range,
                    "edition_uri": edition_uri,
                    "edition_title": edition_title,
                    "arlima_uri": arlima_uri,
                    "notes": notes
                }
                
                # Group the item based on its state
                if div_state == 'near-complete':
                    grouped_listing['near-complete'].append(item)
                elif div_state == 'complete':
                    grouped_listing['complete'].append(item)
                else:
                    grouped_listing['incomplete'].append(item)

# Sort each group of items based on the folio range using a custom sort key
for state in grouped_listing:
    grouped_listing[state].sort(key=lambda item: simple_folio_sort_key(item.get('fol_range', '')))

# Only generate the index if there are items to list
if any(grouped_listing.values()):
    # Render the HTML template with the grouped data
    index_html = index_tmpl.render(
        grouped_listing=grouped_listing,
        project_title="The Texts of BnF fr. 24432", 
        project_subtitle="A cumulative, work-in-progress digital edition"
    )
    # Define the output path for the index
    index_out = os.path.join(OUT_ROOT, "html", "index.html")
    os.makedirs(os.path.dirname(index_out), exist_ok=True)

    # Write the generated index HTML file
    with open(index_out, "w", encoding="utf8") as fh:
        fh.write(index_html)

    print(f"Wrote index -> {index_out}")
else:
    print("No divs found in TEI output folders. Skipping index generation.")