"""The general lab layer: templates, sampling plans, analyses and brain maps over the versioned store.

Templates are data (templates.py). Each sampling plan type has one builder (plans.py) that turns finished runs into
sample, analysis, result and neural_map rows. Nothing here knows about any one study.
"""
