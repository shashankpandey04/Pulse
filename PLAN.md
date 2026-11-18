We need to build a status and incident hub.
Pulse: a product that continuously checks the health of our services, notices when something goes wrong, and opens and tracks an incident until the service recovers. It keeps customers informed through a public status page, and shows the team how reliable each service has been against its target.

Now we will go step by step.

Let's implement this project, such that there will be three different roles for accounts: admin, operator, subscriber

Account Roles:
1) subscriber: When any account is created the account is created only under this category.
2) operator: Accounts with these roles are staff. They are allowed to write into incidents, view metrics, view reliability.
3) admin: This role will have the ability to manage the users, manage service catalogue, manage Service State.

Service Catalogue: Register the services to watch, each with its health URL, how often to check it, its owner and its reliability target.
Manage Users: Can upgrade/downgrade the account roles.
Service States: In this Operator/Admin can decide when a service is healthy, degraded or down, and when it has recovered.
- By default there are three states:
a) Healthy - This state is considered as normal state (Color Code: Green)
b) Down - They can decide after how many no-response from the API endpoint we can consider the API in down state. (Color Code: Red)
c) Slow - How much late response is acceptable that can be configured in this state. (Color Code: Yellow)
d) Flaky - How much percentage of failture rate is acceptable. Anything after that will be considered as flaky state eg. 0.3 means 30% failture rate. (Color Code: Maroon)

*Note: Each account will have: email, password, pfp_link, system generated uid, role, active. Role will be string which can contain any one of the three roles. Active will be boolean, as this is will be responsible to decide if account is active or not*

*Task 1*
Design the Database Schema of Auth, Service Catalogue & Service States.
Design the API Request & Reponse schema of Auth, Service Catalogue, Service States.

Go to `backend` folder in the project and under this create the schema in schemas folder.

We will be using FastAPI, MongoDB (via pymongo), Pydantic, Pydantic[email], bcrypt for password hashing, uvicorn to run FastAPI Server.