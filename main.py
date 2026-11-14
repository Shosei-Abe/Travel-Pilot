from daytona import Daytona, DaytonaConfig

# Define the configuration
config = DaytonaConfig(api_key="dtn_3a8b8d77370d3e2db7b4e6f43b146cbbe71ef7de0b84e5a8624567332d0ea75f")

# Initialize the Daytona client
daytona = Daytona(config)

# Create the Sandbox instance
sandbox = daytona.create()

# Run the code securely inside the Sandbox
response = sandbox.process.code_run('print("Hello World from code!")')
if response.exit_code != 0:
  print(f"Error: {response.exit_code} {response.result}")
else:
    print(response.result)