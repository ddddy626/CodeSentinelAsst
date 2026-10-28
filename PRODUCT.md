# CodeSentinel product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React and Python are confirmed in the supplied plan. This starter uses FastAPI and SQLite locally; MySQL, Redis, and Docker remain planned extensions.

## Users

Developers reviewing Python source, initially through a local web workspace.

## Product Purpose

Find actionable code defects with traceable evidence, an explicit risk level, and a separate evidence strength.

## Operating Context

The first input is one Python file supplied as text or upload. The user reads a report with source locations, tool evidence, uncertainty, and coverage gaps.

## Capabilities and Constraints

The system does not edit submitted source. LLM findings require verification before being presented as confirmed. The long-term system includes multiple agents, three memory layers, rules governance, and authorization controls. The supplied plan leaves V1 acceptance level undecided.

## Product Principles

- Report what the evidence supports.
- Preserve provenance and line locations.
- Expose uncertainty and uncovered areas.
- Keep user data and credentials isolated as the product evolves.
