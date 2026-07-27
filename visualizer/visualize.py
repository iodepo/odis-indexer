import json
from SPARQLWrapper import SPARQLWrapper, JSON

# 1. Verbinding instellen
endpoint_url = "http://localhost:7878/query"
sparql = SPARQLWrapper(endpoint_url)

# Deze query zoekt in de default graph ÉN in alle named graphs
sparql.setQuery("""
    SELECT ?s ?p ?o WHERE {
      { ?s ?p ?o }
      UNION
      { GRAPH ?g { ?s ?p ?o } }
    }
""")
sparql.setReturnFormat(JSON)

try:
    results = sparql.query().convert()
    bindings = results["results"]["bindings"]
    print(f"Aantal gevonden triples: {len(bindings)}")
except Exception as e:
    print(f"Fout bij verbinden: {e}")
    exit()

if len(bindings) == 0:
    print("WAARSCHUWING: Geen data gevonden. Is de database gevuld?")
    # We maken toch de HTML, maar met een melding erin
    message = "GEEN DATA GEVONDEN IN OXIGRAPH"
else:
    message = f"Gevonden triples: {len(bindings)}"

nodes = {}
edges = []

def clean_label(uri):
    # Haalt de laatste bit van een URI op voor leesbaarheid
    label = uri.split('/')[-1].split('#')[-1]
    return label if label else uri

for result in bindings:
    s = result["s"]["value"]
    p = result["p"]["value"]
    o = result["o"]["value"]
    
    # Gebruik de volledige URI als ID, maar een korte label voor de weergave
    if s not in nodes:
        nodes[s] = {"id": s, "label": clean_label(s), "title": s, "color": "#97c2fc"}
    
    # Check of object een URI of Literal is
    is_literal = result["o"].get("type") == "literal"
    if o not in nodes:
        nodes[o] = {
            "id": o, 
            "label": clean_label(o) if not is_literal else o[:30], 
            "title": o,
            "shape": "box" if is_literal else "dot",
            "color": "#eb7df4" if not is_literal else "#ffffc2"
        }
    
    edges.append({"from": s, "to": o, "label": clean_label(p), "title": p})

nodes_js = json.dumps(list(nodes.values()), indent=4)
edges_js = json.dumps(edges, indent=4)

html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Oxigraph Visualization</title>
    <script type="text/javascript" src="../lib/vis-9.1.2/vis-network.min.js"></script>
    <style type="text/css">
        body {{ font-family: sans-serif; }}
        #network {{ width: 100%; height: 800px; border: 1px solid #ccc; background-color: #f9f9f9; }}
        .status {{ padding: 10px; background: #eee; border-bottom: 1px solid #ccc; }}
    </style>
</head>
<body>
    <div class="status"><strong>Status:</strong> {message}</div>
    <div id="network"></div>
    <script type="text/javascript">
        var nodes = new vis.DataSet({nodes_js});
        var edges = new vis.DataSet({edges_js});
        var container = document.getElementById('network');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            edges: {{ arrows: 'to', font: {{ size: 10, align: 'middle' }}, color: '#666' }},
            nodes: {{ font: {{ size: 14 }} }},
            physics: {{ solver: 'forceAtlas2Based', stabilization: true }}
        }};
        var network = new vis.Network(container, data, options);
    </script>
</body>
</html>
"""

output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "oxigraph_graph.html")
with open(output_file, "w") as f:
    f.write(html_content)

print(f"File generated: {output_file}")
