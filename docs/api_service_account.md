# Creating an API Service Account

This document covers how to create a standalone account for making API requests to SotonGPT. This is useful when someone
wants to use SotonGPT as their LLM backend for a separate research application, e.g. a bespoke chatbot. We create a
separate account for this use case so that usage can be tracked without interfering with the user's normal usage or
usage limitations.

A service account of this kind is required to generate an API key. Unfortunately, there is no method for an admin to
generate a generic API key for a user — the user has to log in and generate the API key themselves.

There are two ways to do this: the hard way and the easy way.

- **Easy way**: use an account that can log in via SSO to generate the API key itself. The user can do this themselves.
- **Hard way**: manually create an account in Open WebUI, then use the API to sign in as that user (via password
  authentication) and generate the API key through the Open WebUI API.

## Creating the account

To create an account in Open WebUI, go to the Users panel in the admin settings and press the **+** icon in the top
right. This lets you create a new user with an appropriate name. Set the e-mail and password to whatever you like — this
new user will not be able to log in via the login form, as sign-up has been disabled on the login page (accounts can
only be created and logged into via Southampton SSO).

Use a secure, randomly generated password, and make a note of it, as it will be required to authenticate the account
when generating an API key.

## Generating a session token

Once the account has been created, sign in as the new user via the API to generate a JWT:

```bash
$ curl -X POST http://sotongpt.soton.ac.uk/api/v1/auths/signin \
    -H "Content-Type: application/json" \
    -d '{"email": "service@account.com", "password": "the-password-you-set"}'
{
  "id": "80aacf91-4fc2-4e47-a8b1-af5b04bb89b3",
  "name": "QueerAIServiceAccount",
  "role": "user",
  "email": "ai-ally@soton.ac.uk",
  "profile_image_url": "/api/v1/users/80aacf91-4fc2-4e47-a8b1-af5b04bb89b3/profile/image",
  "token": "---REDACTED---",
  "token_type": "Bearer"
  // ...and loads more data
}
```

You need the value of the `token` field for the next step.

## Generating the API key

Take the session token from above and use it to authenticate against the API to generate an API key:

```bash
$ curl -X POST https://sotongpt.soton.ac.uk/api/v1/auths/api_key \
    -H "Authorization: Bearer SESSION_TOKEN_FROM_STEP_2" \
    -H "Content-Type: application/json"
{"api_key":"---REDACTED---"}
```

Make a note of the API key, as it will not be shown again. If you lose it, repeat the two steps above to generate a new
one.
