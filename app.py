"""
Hugging Face Spaces entrypoint.

Runs the Gradio UI from `ui/gradio_app.py`.
"""

import os

from ui.gradio_app import demo


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    demo.launch(server_name="0.0.0.0", server_port=port)

