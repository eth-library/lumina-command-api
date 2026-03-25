import json
import time

from app.services.transform_eth_udk import run_transform_eth_udk
from app.transformers.eth_udk.step8_json_to_csv import transform as step8


# -------------------------
# CONFIG
# -------------------------
SOURCE_PATH = "test_data/eth-udk.json"
ROOTTERMS_PATH = "test_data/eth-udk-rootterms.json"


# -------------------------
# LOAD INPUT FILES
# -------------------------
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -------------------------
# MAIN TEST
# -------------------------
def main():
    print("🚀 Starting pipeline test...\n")

    start_time = time.time()

    # Load data
    print("📥 Loading input files...")
    source_data = load_json(SOURCE_PATH)
    rootterms_data = load_json(ROOTTERMS_PATH)

    print(f"✅ Loaded {len(source_data)} records\n")

    # Run transformation pipeline
    print("⚙️ Running transformation pipeline...")
    pipeline_start = time.time()

    data = run_transform_eth_udk(source_data, rootterms_data)

    pipeline_time = time.time() - pipeline_start
    print(f"✅ Pipeline finished in {pipeline_time:.2f} seconds\n")

    # -------------------------
    # VALIDATION
    # -------------------------
    print("🧪 VALIDATION")

    print(f"Total records: {len(data)}")

    sample = data[0]

    print("\n🔎 Sample record:")
    for key in [
        "sys",
        "level",
        "descriptor_eng",
        "category_label",
        "root_term"
    ]:
        print(f"{key}: {sample.get(key)}")

    # Check enrichment
    enriched_count = sum(1 for r in data if "descriptor_name" in r)
    print(f"\nEnriched records: {enriched_count}")

    # -------------------------
    # CSV TEST
    # -------------------------
    print("\n📄 Generating CSV...")

    csv_start = time.time()
    csv_content = step8(data)
    csv_time = time.time() - csv_start

    print(f"✅ CSV generated in {csv_time:.2f} seconds")

    # Preview CSV
    print("\n🔎 CSV Preview (first 300 chars):")
    print(csv_content[:300])

    # Count lines
    line_count = csv_content.count("\n")
    print(f"\n📊 CSV lines (incl. header): {line_count}")

    # -------------------------
    # FINAL STATS
    # -------------------------
    total_time = time.time() - start_time

    print("\n🏁 FINAL SUMMARY")
    print(f"Pipeline time: {pipeline_time:.2f}s")
    print(f"CSV time: {csv_time:.2f}s")
    print(f"Total time: {total_time:.2f}s")

    print("\n✅ Pipeline test completed successfully.")


# -------------------------
# RUN
# -------------------------
if __name__ == "__main__":
    main()