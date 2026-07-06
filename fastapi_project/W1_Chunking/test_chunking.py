from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Simulate your factory SOP text
sop_text = """
SOP-03: STENTER MACHINE TEMPERATURE SETTING (POLYESTER FABRIC PRE-SETTING)
To prevent polyester fabric from excessive shrinkage above 2%, the operator must set the stenter machine oven temperature between 180°C and 190°C. The fabric draw duration inside the oven must be consistently maintained between 30 to 45 seconds only.

SOP-09: CUSTOMER FABRIC DAMAGE COMPENSATION POLICY
If damage to greige makloon fabric caused by the jet dyeing machine bursting or jamming exceeds 10 percent of the total order volume, the makloon factory is required to provide compensation equal to the value of the damaged raw greige fabric to the customer. Management is not liable for losses caused by third-party negligence.
"""

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=300,      # Target character length per chunk
    chunk_overlap=50,    # Context overlap between neighboring chunks
    length_function=len,
)

# 3. Execute Text Splitting
chunks = text_splitter.create_documents([sop_text])

# 4. Display Results in Terminal
print(f"Total chunks generated: {len(chunks)}\n")
for i, chunk in enumerate(chunks):
    print(f"--- CHUNK {i+1} (Length: {len(chunk.page_content)} characters) ---")
    print(chunk.page_content)
    print("-" * 40, "\n")
