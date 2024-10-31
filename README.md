# StackOverflow Scraper API

## Overview

This project implements a REST API that replicates the functionality of specific endpoints described in the StackExchange API specification, specifically for StackOverflow. The API is built using Python and Flask, and it scrapes data from the StackOverflow website using BeautifulSoup.

## Features

- Implements the following endpoints:
  - `/collectives`: Returns a list of Collective objects.
  - `/questions`: Returns a list of Question objects.
  - `/questions/{ids}`: Returns a list of Question objects identified by ids.
  - `/answers/{ids}`: Returns a list of Answer objects identified by ids.
  - `/questions/{ids}/answers`: Returns a list of Answer objects related to specified questions.
  
- Supports built-in filters described by the StackExchange API specification.
  - `withbody`, `none`, `total`  
- Accepts query parameters:
  - `min`, `max`, `fromdate`, `todate`, `sort`
- Implements paging as specified in the StackExchange API documentation.

