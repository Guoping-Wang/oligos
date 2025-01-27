from flask import Flask, request, jsonify
import requests
import subprocess
import time

app = Flask(__name__)

# NCBI BLAST API URL
NCBI_BLAST_URL = "https://blast.ncbi.nlm.nih.gov/Blast.cgi"

# Primer QC Functionality
def get_reverse_complement(sequence):
    """Generate the reverse complement of a DNA sequence."""
    complement_map = {"A": "T", "T": "A", "G": "C", "C": "G"}
    return "".join(complement_map[base] for base in sequence[::-1])

def check_heterodimer(primer1, primer2):
    """Check for complementary regions between two primers."""
    rev_comp_primer2 = get_reverse_complement(primer2)
    for i in range(len(primer1)):
        for j in range(len(rev_comp_primer2)):
            if primer1[i:i+4] == rev_comp_primer2[j:j+4]:
                return True
    return False

@app.route("/primer_qc", methods=["POST"])
def primer_qc():
    """Handle Primer QC requests."""
    data = request.get_json()
    primer1 = data.get("primer1", "").strip().upper()
    primer2 = data.get("primer2", "").strip().upper()

    if not primer1 or not primer2:
        return jsonify({"error": "Both primers are required."}), 400

    result = {
        "primer1_length": len(primer1),
        "primer2_length": len(primer2),
        "heterodimer": check_heterodimer(primer1, primer2)
    }

    return jsonify(result)

# BLAST Functionality
@app.route("/run_blast", methods=["POST"])
def run_blast():
    """Handle BLAST requests."""
    data = request.get_json()
    sequence = data.get("sequence", "").strip()
    program = data.get("program", "blastn")
    database = data.get("database", "nt")

    if not sequence:
        return jsonify({"error": "No sequence provided."}), 400

    # Step 1: Submit the BLAST request
    params = {
        "CMD": "Put",
        "PROGRAM": program,
        "DATABASE": database,
        "QUERY": sequence,
    }
    response = requests.post(NCBI_BLAST_URL, data=params)

    if response.status_code != 200:
        return jsonify({"error": "Failed to submit BLAST request to NCBI."}), 500

    # Extract the Request ID (RID)
    rid = None
    for line in response.text.split("\n"):
        if line.startswith("RID ="):
            rid = line.split("=")[1].strip()
            break

    if not rid:
        return jsonify({"error": "Failed to retrieve RID from NCBI response."}), 500

    # Step 2: Wait for results
    while True:
        status_params = {
            "CMD": "Get",
            "RID": rid,
            "FORMAT_TYPE": "JSON"
        }
        status_response = requests.get(NCBI_BLAST_URL, params=status_params)
        if "Status=WAITING" in status_response.text:
            time.sleep(5)
        elif "Status=READY" in status_response.text:
            if "ThereAreHits=yes" in status_response.text:
                break
            else:
                return jsonify({"error": "No hits found for the query sequence."}), 200
        else:
            return jsonify({"error": "Failed to retrieve BLAST results."}), 500

    # Step 3: Retrieve results
    results_response = requests.get(NCBI_BLAST_URL, params={
        "CMD": "Get",
        "RID": rid,
        "FORMAT_TYPE": "JSON"
    })

    if results_response.status_code != 200:
        return jsonify({"error": "Failed to retrieve BLAST results."}), 500

    return jsonify({"results": results_response.json()})

if __name__ == "__main__":
    app.run(debug=True)