
from urllib.parse import urlparse, parse_qs

def toggle_whatsapp_prefix(input_string):
    prefix = "whatsapp:"
    if input_string.startswith(prefix):
        return input_string[len(prefix):]
    else:
        return prefix + input_string

def extract_url_and_table_param(url):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
    
    query_params = parse_qs(parsed_url.query)
    table_param = query_params.get('table', [None])[0]

    return base_url, table_param
