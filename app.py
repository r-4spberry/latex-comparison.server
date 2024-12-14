from flask import Flask, request, jsonify
from flask_restx import Api, Resource, fields, reqparse
from difflib import SequenceMatcher
import os
from PyPDF2 import PdfReader
import torch
from PIL import Image
from pix2tex.cli import LatexOCR
import tempfile
from werkzeug.datastructures import FileStorage
from flask_cors import CORS
from latex_to_maxim import sympy_to_custom
from sympy.parsing.latex import parse_latex
from sympy.parsing.latex.errors import LaTeXParsingError

app = Flask(__name__)
CORS(app)

api = Api(
    app,
    version="1.0",
    title="LaTeX API",
    description="An API for handling LaTeX comparisons and conversions",
)

ocr_model = LatexOCR()

ns = api.namespace("api", description="LaTeX operations")

file_upload_parser = reqparse.RequestParser()
file_upload_parser.add_argument(
    "file", type=FileStorage, location="files", required=True, help="File to upload"
)


# Define models for Swagger documentation
compare_model = api.model(
    "CompareModel",
    {
        "latex1": fields.String(required=True, description="First LaTeX string"),
        "latex2": fields.String(required=True, description="Second LaTeX string"),
    },
)


@ns.route("/compare")
class Compare(Resource):
    @api.expect(compare_model)
    def post(self):
        """Compare two LaTeX strings"""
        data = request.get_json()
        if not data or "latex1" not in data or "latex2" not in data:
            return {"error": "Missing LaTeX strings"}, 400
        latex1 = data["latex1"]
        latex2 = data["latex2"]
        print(f"{latex1=}, {latex2=}")
        try:
            try:
                latex1_transformed = sympy_to_custom(parse_latex(latex1))
            except ValueError or LaTeXParsingError as e:
                return {"error": f"latex1: {str(e)}"}, 409
            try:
                latex2_transformed = sympy_to_custom(parse_latex(latex2))
            except ValueError or LaTeXParsingError as e:
                return {"error": f"latex2: {str(e)}"}, 409
        except Exception as e:
            return {"error": str(e)}, 500
        similarity = (
            SequenceMatcher(None, latex1_transformed, latex2_transformed).ratio() * 100
        )
        return {"similarity": f"{similarity:.2f}%"}


@ns.route("/operations")
class Operations(Resource):
    def get(self):
        """List all supported LaTeX operations"""
        return {
            "latex_operations": [
                "frac",
                "+",
                "-",
                "*",
                "/",
                "^",
                "_",
                "sqrt",
                "sum",
                "int",
                "left",
                "right",
                "cdot",
                "times",
                "log",
            ]
        }


@ns.route("/pdf2latex")
class PdfToLatex(Resource):
    @api.expect(file_upload_parser)
    def post(self):
        """Extract LaTeX formulas from a PDF"""
        args = file_upload_parser.parse_args()
        file = args["file"]
        if not file:
            return {"error": "No file provided"}, 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            file.save(tmp_file.name)
            file_path = tmp_file.name

        try:
            extracted_formulas = []
            reader = PdfReader(file_path)
            for page in reader.pages:
                text = page.extract_text()
                extracted_formulas.extend(
                    [line for line in text.splitlines() if "\\" in line]
                )
        except Exception as e:
            os.remove(file_path)
            return {"error": str(e)}, 500

        os.remove(file_path)
        return {"formulas": extracted_formulas}


@ns.route("/pix2tex")
class PixToTex(Resource):
    @api.expect(file_upload_parser)
    def post(self):
        """Extract LaTeX formulas from an image"""
        args = file_upload_parser.parse_args()
        file = args["file"]
        if not file:
            return {"error": "No file provided"}, 400

        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
            file.save(tmp_file.name)
            file_path = tmp_file.name

        try:
            image = Image.open(file_path).convert("RGB")
            latex_formula = ocr_model(image)
            extracted_formulas = [latex_formula]
        except Exception as e:
            os.remove(file_path)
            return {"error": str(e)}, 500

        try:
            converted = sympy_to_custom(parse_latex(latex_formula))
        except Exception as e:
            os.remove(file_path)
            return {
                "error": f"couldn't parse the string {latex_formula}, {str(e)}"
            }, 409

        os.remove(file_path)
        return {"formulas": extracted_formulas}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
