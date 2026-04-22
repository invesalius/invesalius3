# Fix: Surface Colour/Transparency KeyError Crash

## Issue
Changing the surface colour or transparency in Preferences crashes the application with `KeyError: -1` when no surface is selected.

## Root Cause
`SetActorColour()` and `SetActorTransparency()` in `invesalius/data/surface.py` access `self.actors_dict[surface_index]` without checking if `surface_index` is valid. When no surface is selected, the index is `-1`, which doesn't exist in the dictionary.

## Steps to Reproduce
1. Open InVesalius and load any DICOM dataset.
2. Go to **Preferences** → **TMS Motor Mapping** tab.
3. Click the colour picker button next to the brain surface dropdown **without selecting any surface** from the dropdown.
4. Pick any colour → **crash** with `KeyError: -1`.

## Fix
Added early-return guards in both `SetActorTransparency()` and `SetActorColour()` to skip the operation when `surface_index` is not present in `actors_dict`.

```diff
  def SetActorTransparency(self, surface_index, transparency):
+     if surface_index not in self.actors_dict:
+         return
      self.actors_dict[surface_index].GetProperty().SetOpacity(1 - transparency)

  def SetActorColour(self, surface_index, colour):
+     if surface_index not in self.actors_dict:
+         return
      self.actors_dict[surface_index].GetProperty().SetColor(colour[:3])
```
