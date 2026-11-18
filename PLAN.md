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

| Service | Address | Health check |
| --- | --- | --- |
| `quotes` | http://localhost:7001 | http://localhost:7001/health |
| `payments` | http://localhost:7002 | http://localhost:7002/health |
| `claims` | http://localhost:7003 | http://localhost:7003/health |
| `notifications` | http://localhost:7004 | http://localhost:7004/health |
| Webhook receiver | http://localhost:9900 | Stands in for chat, email and paging. Anything POSTed to it appears on its page. `GET /api/received` returns the list as JSON; `DELETE /api/received` clears it. |


*Task 2*
Create required client using pymongo in core/database.py

Wire routers/auth.py, catalogue.py, and state.py to MongoDB with bcrypt hashing and role-based access.
These API should have all required CRUD endpoints with role based access control.
Create a central role based access in core/dependencies.py which will have all required function or decorator for RBAC.
In core/jwt.py, write the required functions which are required to issue, verify JSON Web Tokens for the frontend client. For this use `jwt` library which is installed using `pip install pyjwt`
After this write the routers/auth.py, catalogue.py & state.py

Along with this our continued task is:
Health Check CRON Job: It's job is to run the health checks from our service catalogue and perform required actions like automated open/close of indidents, it will run along with our FastAPI Using apscheduler (installed via `pip install apscheduler`) AsyncIOScheduler running directly on FastAPI's asyncio event loop inside FastAPI's lifespan context manager. Check every service on its own schedule, without one slow service holding up the others. Store every result.
*Tip: Avoid the older @app.on_event("startup") decorator, as FastAPI recommends lifespan for managing startup and shutdown resources.*

*To know:* Webhook receiver | http://localhost:9900 | Stands in for chat, email and paging. Anything POSTed to it appears on its page. `GET /api/received` returns the list as JSON

To create the required schemas for Incidents, Metrics, Reliability.
1) Incidents: Our CRON Job can open an incident automatically when a service goes down, and close it when it recovers. And someone can acknowledge it and add notes. Each incident has a timeline of what happened. Notes are by default saved as public. If marked public then it's also visible on public status page.
2) Metrics: Shows how quickly problems are detected and resolved, and how the checking itself is performing.
3) Reliability: Show each service's availability over time against its target, and how much room for failure is left.
4) Notifications: Notify the webhook receiver when an incident opens and when it resolves.

*Task 3*
Implementation of incidents/metrics/reliability/public routers + dashboard API with RBAC

Now we will implement the API Endpoints which are required to view/update/create the operations as per the module with respect to their roles.

Along with that, also implement Dashboard API, which returns the data as per user roles.

After that we will move to frontend development mainly. With a few part of backend development.

*Task 4*
Now let's create the frontend for this project.
Tech Stack: NextJS + Zod

Instructions: 
- The frontend should be minimal black & white.
- No unwanted UI Badge, Pills
- It should have good contrast, with boxy UI.
- Carefully implement the backend API integration.
- Don't directly call the Backend API Endpoints from pages. Create seperate self hosted NextJS API's to connect with backend API endpoints.
- Don't add and run unnecessary tests, animations, library. Only add those which are actually necessary for the frontend.
- And cover & build all the necessary pages which are required for fully functional website. 