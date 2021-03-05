# ToolShare
This repository started as a place to document my CS50 final project, but has developed into the source code for deploying the web app on Heroku at [toolshare.tk](https://sharetools.tk).

If you wish to fork this and host your own tool-share instance, you will need the following resources (and if you use my same ones it can be completely free!):
  1. Hosting/deployment service
  2. File storage location
  3. Email account
  4. Domain registration (optional)
  5. DNS service (optional)

\
For the above list
  * [Heroku](https://www.heroku.com/) account (hobby) with PostgreSQL database "Add-on"
  * [AWS S3](https://aws.amazon.com/s3/pricing/) (free tier)
  * New [Gmail account](https://accounts.google.com/SignUp?hl=en) for the app, set to "Allow less secure apps"
  * [Freenom](https://www.freenom.com/en/index.html?lang=en) to get a domain name
  * [Cloudflare](https://www.cloudflare.com/) for DNS service and SSL connection to Heroku

---
Eventually, I may add a full "how to" for setting up your own tool-share, but for now I just have some notes on the process.

---

## Implementation Notes:
  - Unique configuration details can be set in the `Config.py` file (like email and AWS S3 bucket name)
  - Secrets (passwords and keys) are stored in local environment variables.

### Setting Environment Variables:
#### Mac:
>(make sure you are inside the flask virtual environment "venv")
```
export AWS_ACCESS_KEY_ID=xxx
export AWS_SECRET_ACCESS_KEY=yyy
export MAIL_PASSWORD='zzz'
```

#### Heroku:
>(after the Heroku CLI is installed and setup)
```
heroku config:set AWS_ACCESS_KEY_ID=xxx AWS_SECRET_ACCESS_KEY=yyy MAIL_PASSWORD='zzz'
```
