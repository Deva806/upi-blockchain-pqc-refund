import subprocess

exe_path = r"C:\Users\devad\OneDrive\Desktop\UPI\quantum_module\quantum.exe"

# Run the quantum module
result = subprocess.run([exe_path], capture_output=True, text=True)

print("Quantum module output:")
print(result.stdout)
