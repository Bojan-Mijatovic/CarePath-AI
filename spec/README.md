# spec

Owner: R5. The contracts every role builds against.

- `SPEC.md`: data, state, tool, action, API and WebSocket contracts; acceptance criteria AC1–AC19.
- `pathways/`: pathway model JSON (`hf_lombardia_v1.json`, later diabetes) and its JSON schema.
- `pdta/`: PDTA source texts in Italian (`*.it.md`, the input of the Pathway Builder) with English reference translations (`*.en.md`): heart failure final, type 2 diabetes draft (option B). `testing/test_pdta_texts.py` keeps the HF text in line with `pathways/hf_lombardia_v1.json` and the two languages in line with each other.

Contracts freeze at tag `spec-v1` (step 1.9). After that, changes go through the sync and the decision register.
