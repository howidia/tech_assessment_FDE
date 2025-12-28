.PHONY: setup run eval clean

# Create env and install dependencies
setup:
	python3 -m venv venv
	@echo "✅ Virtual environment created."
	@echo "Activate venv with: source venv/bin/activate"
	@echo "Then run: pip install -r requirements.txt"

# Run the interactive CLI
run:
	python main.py

# Run the evaluation pipeline
eval:
	python evaluate.py

# Remove generated reports
clean:
	rm -rf reports/*
	@echo "🗑️ Reports cleaned."