# Compiled delegates for the KSA control inputs

The KSA `Services/Control.cs` reads and writes `Vehicle._manualControlInputs` through a `FieldInfo`. Each get boxes the struct, and each set boxes it twice. The field is used on every control input get and set.

Replace the `FieldInfo` with a typed getter and setter from `KRPC.Utils.Accessor`, compiled once when the class loads:

```csharp
static readonly Field<global::KSA.Vehicle, ManualControlInputs> manualControlInputs =
    Accessor.Field<global::KSA.Vehicle, ManualControlInputs> ("_manualControlInputs");
```

The KSP services already access private game members this way. `Accessor.Field` returns null when the member is missing, so log a warning when it does, as the KSP services do.

**Blocked on** a `KRPC.Core` release that includes `Accessor`. The KSA mod builds against the released `KRPC.Core` package.

## Testing

The KSA `test_control.py` covers the control inputs.
