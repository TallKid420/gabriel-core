# Python Notes

## f-string `!r` (repr conversion flag)

In Python f-strings, `!r` tells Python to use `repr()` on a value before formatting it.

### Example

```python
name = "Gabriel"

print(f"{name}")     # uses str()
print(f"{name!r}")   # uses repr()
```

### Output

```output
Gabriel
'Gabriel'
```
