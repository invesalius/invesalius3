import invesalius_rs._native as _native
print("Attributes in _native:")
for attr in sorted(dir(_native)):
    if not attr.startswith("__"):
        print(f"  - {attr}")

missing = "floodfill_voronoi_inplace"
if hasattr(_native, missing):
    print(f"\nSUCCESS: {missing} found!")
else:
    print(f"\nFAILURE: {missing} NOT found!")
    
import invesalius_rs
print(f"\ninvesalius_rs attributes:")
for attr in sorted(dir(invesalius_rs)):
    if not attr.startswith("__"):
        print(f"  - {attr}")
