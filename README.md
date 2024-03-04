Python ISS Tracker Using Online NASA Data

This folder contains Python scripts and a Dockerfile to run them in a containerized environment.
The iss_tracker.py script fetches data about ISS movements from NASA and returns the following data in JSON format through an API

The NASA data is sourced [here](https://spotthestation.nasa.gov/trajectory_data.cfm)

- The comments on the current ISS data from NASA (`curl localhost:5173/comment`)
- The header from the current ISS data from NASA (`curl localhost:5173/comment`)
- The metadata from the current ISS data from NASA (`curl localhost:5173/metadata`)
- All data currently available from NASA (`curl localhost:5173/epochs`)
  - 'limit' and 'offset' optional query parameters can be used to restrict how many results are returned and from where in the dataset the results begin
- A specific epoch from the current NASA dataset (`curl localhost:5173/epochs/<epoch>`)
  - `<epoch>` should be an index in the dataset or a timestamp formatted as `%Y-%jT%H:%M:%S.%fZ`
- The speed of a specific epoch from the current NASA dataset (`curl localhost:5173/epochs/<epoch>/speed`)
  - `<epoch>` should be an index in the dataset or a timestamp formatted as `%Y-%jT%H:%M:%S.%fZ`
- The location of a specific epoch from the current NASA dataset (`curl localhost:5173/epochs/<epoch>/location`)
  - `<epoch>` should be an index in the dataset or a timestamp formatted as `%Y-%jT%H:%M:%S.%fZ`
- The most current state of the ISS and the ISS's speed and location from the current NASA dataset (`curl localhost:5173/now`)

Epoch JSON type format, referred to as Epoch type in below JSON type structures

```
{
   "timestamp": String,
   "x": number,
   "y": number,
   "z": number,
   "dx": number,
   "dy": number,
   "dz": number
}
```

Position values are in km and velocity values are in km/s
If a value in the header or metadata is a date, it will be converted to a datetime object.
In the JSON response it will be a human-readable datetime string.

Endpoint responses are structured as follows

- `/comment`
  ```
  {
     "comments": [String]
  }
  ```
- `/header`
  ```
  {
     "header": object
  }
  ```
- `/metadata`
  ```
  {
     "metadata": object
  }
  ```
- `/epochs`
  ```
  {
     "data": [Epoch]
  }
  ```
- `/epochs/<epoch>`
  ```
  {
     "epoch": Epoch|null
  }
  ```
- `/epochs/<epoch>/speed`
  ```
  {
     "speed": number
  }
  ```
- `/epochs/<epoch>/location`
  ```
  {
     "location": {
         "lat": number,
         "lon": number,
         "altitude": number
     }
  }
  ```
- `/now`
  ```
  {
     "epoch": Epoch,
     "speed": number,
     "location": {
         "lat": number,
         "lon": number,
         "altitude": number
     }
  }
  ```

The test_iss_tracker.py script includes full unit tests for iss_tracker.py

This code is offered in a Docker container so that it works reliably across systems. To utilize this program, do the following

1. Have Docker installed
2. Set the working directory to this folder (`coe332midterm`)
3. Running the service

   `docker-compose run serve`

4. Running the tests

   `docker-compose run test`
