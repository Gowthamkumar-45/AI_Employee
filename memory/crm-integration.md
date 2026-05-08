# CRM Integration Guide

This file explains how to connect the AI employee progress to Freshworks CRM.

## Why Freshworks

Freshworks CRM can show your pipeline visually and keep lead stages updated in one place.

## Mapping fields

Use these Freshworks fields to mirror `memory/pipeline.md`:

- Lead name
- Company
- Role
- Email
- Phone number
- LinkedIn profile
- Social media profiles
- Current stage (scouted, qualified, outreach, follow-up, booked, met, won, lost)
- Next step
- Notes / status details

## How to connect

1. create a lead record in Freshworks for each lead in `memory/pipeline.md`
2. update the Freshworks stage after every lead interaction
3. keep the CRM notes aligned with the pipeline notes and verification status
4. use Freshworks automations or workflows for alerts on stage change

## Automation options

- use Freshworks API to push lead updates from your tracking system into Freshworks
- use Zapier / Make / n8n to sync a spreadsheet or webhook into Freshworks
- if you use a sheet as an intermediate source, map it to Freshworks automatically
- use `scripts/freshworks_sync.py` as a starter integration script to push progress into Freshworks

## Monitoring

- visually review the Freshworks pipeline board for current lead stages
- confirm each lead status matches `memory/pipeline.md`
- use Freshworks alerts or Slack for closed-won / closed-lost notifications

## Notes

- this repo does not include a direct Freshworks connector
- the AI employee should keep `memory/pipeline.md` updated and then sync that data into Freshworks
- if you want, create a Freshworks dashboard that reads the same stage fields from the CRM
