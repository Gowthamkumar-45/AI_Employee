# Freshworks Integration

This file explains how to connect your AI employee progress to your Freshworks CRM account.

## What this does

- keeps Freshworks updated with lead progress
- mirrors `memory/pipeline.md` to CRM stages
- lets you monitor progress visually in Freshworks

## Setup

1. get your Freshworks domain and API key
2. add them to your environment:
   - `export FRESHWORKS_DOMAIN="yourcompany"`
   - `export FRESHWORKS_API_KEY="your_api_key"`
3. prepare a lead export file, for example `leads.json`
4. run:
   - `python3 scripts/freshworks_sync.py leads.json`

## Lead fields

The sync expects lead objects with:

- `name`
- `company`
- `email`
- `phone`
- `linkedin`
- `stage`
- `next_step`
- `notes`

## How to use

- update `memory/pipeline.md` as the AI employee progresses
- export the lead data into a structured JSON file
- run `scripts/freshworks_sync.py` to push the records to Freshworks
- use Freshworks to view the pipeline and track stages visually

## Notes

- the repo does not have direct access to your Freshworks account credentials
- you need to provide the API key and domain for the script to work
- this is a starting point; you can extend the script to update existing leads instead of creating new ones
