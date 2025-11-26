# Overview

Two files do the majority of the work the [CSV Importer](https://github.com/nemotests/nimbus/blob/main/openchargemap_import_csv.py) downloads and converts the JSON payload from the API into a flat structure.

I didn't want to use a JSON structure in BigQuery because I worry about performance of nested JSON in queries. 


The [GCS uploader](https://github.com/nemotests/nimbus/blob/main/gcs_uploader.py) takes the CSV data, uploads it to GCS to create a store, pushes it into Big Query and then adds the extra columns needed for Geography and Looker Studio


# Setup:

Would obviously flesh out with more time but simple instructions would be: 

Pull the repo

Populate the sample env file and rename to .env

Ensure CLI Gcloud path varible set

Run

Things I would do if I had more time: More comprehsive docs and fix the requirements against specific verisons to improve stability.


# Thought process
## Datasets
For datasets I initially thought I was going to use the National Charge Point Registry, but that was de-commissioned last year. OSM or Overture looked like good possible options but they lacked some the attribution consistency I think people would want.

Open Charge Map looked like a good option and the API was serviceable if a little frustrating to get started with. 

All of the above have open permissible data licenses, Open Charge Map uses creative commons. Has a global coverage, I think the update frequency needs addressing but overall the data looked good in terms of attribution.

I think regardless of source you would probably want to create a blended harmonised dataset from a variety of sources including Overture etc. 

## Tooling
If you were going to productionise a data pipeline I wouldn’t go down the route I did for the task, an orchestrator tool would be more appropriate, something like Airflow,Dagster or Apache Nifi.
For the limited time allotted to the task creating a set of python scripts seemed like the easier option. If you wanted to productionise a cron job would let you have this running automatically obviously it could be orchestrated in a more controlled way than a cron job with more time. 

Filter to London we could use Postcode or the geometry location. When pulling the data I used a tiled fetch approach around the M25 area. 
The easiest method would probably be to use OS Boundary line, using the relevant polygon for Central London to do a simple attribute flag in the data using a point in polygon query. 

## Data Validation
The scripts to limited data validation, I think given more time I would create a meta data catalogue that included assumptions around each dataset you wanted to import, factors would include:
•	Estimated expected number of rows
•	Coverage
•	SRIDs
•	Temporality 
•	Null value ratios

Strong schemas would let you verify the data on ingestion but erroneous data could easily slip through, comparing this ingested batch of data against the last one seems sensible, also storing the change only update versions of the data could let you track potential errors and fix them. 
For spatial coverage a geohash created from the lat,long values rounded up for precision could easily let you spot potential gaps in the data for instance


## Dashboards
I looked at Superset but Superset has limited location based dashboarding functionality, it’s also based on Deck.GL which is notoriously hard to use. 

Looker Studio seemed like a good option as it sticks to the Google ecosystem and was super easy to get up and running and very customisable as long as the data schema was setup in the right way. 

Link: https://lookerstudio.google.com/s/ijbfnCT5NU4

<img width="3419" height="1287" alt="Screenshot 2025-11-26 124238" src="https://github.com/user-attachments/assets/5b6757ce-9db8-489c-b5ab-677b9b70a134" />

