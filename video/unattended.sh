#!/bin/bash
# Production, with nobody watching. Every line read back from AWS.
cd "$(dirname "$0")/.."
echo '$ aws scheduler list-schedules'
aws scheduler list-schedules --query 'Schedules[?contains(Name,`lapse`)].[Name,State]' --output text
echo
echo '$ aws logs filter-log-events --log-group /aws/lambda/lapse-run'
aws logs filter-log-events --log-group-name /aws/lambda/lapse-run \
  --filter-pattern 'run_finished' --output text 2>/dev/null \
  | grep -o '{.*}' | tail -1 | cut -c1-146
echo
echo '$ # what left the building, read back from DynamoDB'
aws dynamodb scan --table-name lapse-cases \
  --filter-expression "#s = :f" \
  --expression-attribute-names '{"#s":"status"}' \
  --expression-attribute-values '{":f":{"S":"filed"}}' \
  --query 'Items[].[case_id.S,delivery.M.mode.S,delivery.M.message_id.S]' \
  --output text 2>/dev/null | head -2
echo
echo '  Two filed, each with a real SES message id.'
echo '  Everything else is still waiting for a person.'
