# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = 'Chatbot Testing and Tracing Framework'
copyright = '2025, Olex Ostrovskyy'
author = 'Olex Ostrovskyy'
release = '0.1.11'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [                                                                                                 
    'myst_parser',  # Enable Markdown parsing                                                                  
    'sphinx.ext.autodoc', # For pulling docs from docstrings (optional but good)                               
    'sphinx.ext.napoleon' # For Google/Numpy style docstrings (optional but good)                              
] 

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = 'alabaster'
html_theme = 'furo'
html_static_path = ['_static']
