"""Validates requests for BraTS data access.

Per the rules of the BraTS Challenges (2023 and beyond), participants must:
    1. register for the challenges; AND
    2. complete a "mailing list" Google form

before they can access the challenge data. This script performs these checks
and, if all criteria are met, sends an invite to the BraTS Data Access Team,
thus granting access to the data.
"""

import time
from datetime import datetime

import gspread
import pandas as pd
import synapseclient

# Google Form config
# ---------------------------------------------------------------------
GOOGLE_SHEET_TITLE = "BraTS Data Access Responses"
RESPONSES_SPREADSHEET = "2025 and beyond"
LOGS_SPREADSHEET = "Logs"

# Synapse config
# ---------------------------------------------------------------------
CHALLENGE_NAME = "BraTS-Lighthouse 2025"  # TODO: update with latest Challenge name.
CHALLENGE_TEAM_ID = 3523569  # TODO: update with latest teamID for Participant team.
DATA_ACCESS_TEAM_ID = 3523636  # !!! Do not change.
EMAIL_TEMPLATES = {
    "Access already granted": (
        "You have already joined the BraTS Data Access Team. To download "
        "the data, please go to the 'Files' tab of the challenge website."
    ),
    "Pending invite": (
        "An email invite to join the BraTS Data Access Team has already been "
        "sent.  Please check your inbox or spam folder for an email from the "
        "BraTS Bot account (brats-fets-bot@synapse.org)."
    ),
    "Missing registration": (
        "You must first register and agree to the Terms & Conditions of the "
        f"latest BraTS Challenge:<br/><br/>> {CHALLENGE_NAME}<br/><br/>If you "
        "are still interested in gaining access to the data, please register "
        "for the challenge listed above, then re-submit the Google Form."
    ),
}


def add_result_to_logs(wks, original_timestamp: str, username: str, result: str):
    """Logs the validation result into the given Google worksheet.

    Assumption:
        Google worksheet has four columns in the following order:
            1. timestamp of logging message
            2. timestamp of form response
            3. Synapse username
            4. log message
    """
    now = datetime.now().strftime("%m/%d/%Y %H:%M:%S")
    new_row = [now, original_timestamp, username, result]
    wks.append_row(new_row)


def is_valid_synapse_user(username: str) -> dict | None:
    """Checks if the given username is a real Synapse account."""
    try:
        # If username is digits only, use another method to verify.
        if username.isdigit():
            return [
                user
                for user in syn.restGET(f"/userGroupHeaders?prefix={username}").get(
                    "children"
                )
                if user.get("userName") == username
            ][0]
        return syn.getUserProfile(username)
    except synapseclient.core.exceptions.SynapseHTTPError as err:
        if "UserProfile cannot be found" in str(err):
            team_id = syn.getTeam(username).id
            send_invalid_email(username, team_id, "Username not provided")
        return None
    except (ValueError, IndexError):
        return None


def is_team_member(team_id: int, user_id: str) -> bool:
    """
    Checks if the given Synapse user is already part of the given Synapse team.
    """
    try:
        syn.restGET(f"/team/{team_id}/member/{user_id}")
        return True
    except synapseclient.core.exceptions.SynapseHTTPError:
        return False


def get_open_invites(team_id: int) -> list:
    """
    Returns a list of user IDs with pending invites to the given Synapse team.
    """
    return [
        invite.get("inviteeId") for invite in syn.get_team_open_invitations(team_id)
    ]


def send_email_invite(team_id: int, user_id: str) -> str:
    """Invite the given Synapse user to join the given Synapse team."""
    try:
        invite = (
            "Thank you for your interest in the BraTS data! After clicking 'Join', you "
            "can start downloading data from the 'Files' tab of the BraTS Challenge "
            "websites."
        )
        syn.invite_to_team(team=team_id, user=user_id, message=invite)
        log_msg = "Invite sent"
        time.sleep(2)  # Add buffer time to prevent too-frequent API calls.
    except Exception as err:
        log_msg = f"Error sending invite: {err}"
    return log_msg


def send_invalid_email(username: str, user_id: str, err_level: str):
    """Send an email to the given Synapse user with the validation results."""
    subject = f"BraTS Data Access Form - {err_level}"
    message = f"Dear {username},<br/><br/>"
    message += EMAIL_TEMPLATES.get(err_level)
    message += "<br/><br/>Sincerely,<br/>BraTS Bot"
    syn.sendMessage(
        userIds=[user_id],
        messageSubject=subject,
        messageBody=message,
        contentType="text/html",  # Enable HTML content
    )
    time.sleep(2)  # Add buffer time to prevent too-frequent API calls.


def validate_response(response: pd.Series, open_invites: list) -> str:
    """Validate the current form response and send email if invalid.

    Checks include:
        1. Is the given username a real Synapse account?
        2. Has access already been granted to the user?
        3. Did the user already register for the latest challenge?
        4. Is there already a pending invite for the user?
    """

    # Typecast to string, in case username is digits only.
    submitted_username = str(response["Synapse Username"]).strip()

    # First check: valid Synapse username?
    if profile := is_valid_synapse_user(submitted_username):
        syn_userid = profile.get("ownerId")

        # Second check: has access already been granted?
        if is_team_member(DATA_ACCESS_TEAM_ID, syn_userid):
            result = "Access already granted"

        # Third check: did user register for the challenge?
        elif is_team_member(CHALLENGE_TEAM_ID, syn_userid):

            # Final check: invite already sent? If not, send invite.
            result = (
                "Pending invite"
                if syn_userid in open_invites
                else send_email_invite(DATA_ACCESS_TEAM_ID, syn_userid)
            )

        else:
            result = "Missing registration"

        if result != "Invite sent":
            send_invalid_email(submitted_username, syn_userid, result)
        return result

    return "Username not found"


def main():
    """Main function: check form responses and send invites as needed.

    Assumptions:
        - form responses worksheet contains two columns: `Timestamp` and
          `Synapse Username`
        - logs worksheet contains two columns: `Original Timestamp` and
          `Synapse Username`
    """

    # Get form responses and put them into a DataFrame.
    gc = gspread.service_account(filename="service_account.json")
    google_sheet = gc.open(GOOGLE_SHEET_TITLE)
    responses_df = pd.DataFrame(
        google_sheet.worksheet(RESPONSES_SPREADSHEET).get_all_records()
    )[["Timestamp", "Synapse Username"]]

    # Because the logs spreadsheet will be updated, it must first be
    # retrieved as a gspread.Worksheet before put into a DataFrame.
    logs_wks = google_sheet.worksheet(LOGS_SPREADSHEET)
    logs_df = pd.DataFrame(logs_wks.get_all_records())[
        ["Original Request Timestamp", "Synapse Username"]
    ]

    # Only validate new responses, by comparing the (timestamp + username)
    # of the form responses against the (original timestamp + username)
    # of the logs worksheet.
    new_responses = responses_df.merge(
        logs_df.rename(columns={"Original Request Timestamp": "Timestamp"}),
        on=["Timestamp", "Synapse Username"],
        how="left",
        indicator=True,
    ).query('_merge == "left_only"')

    if new_responses.empty:
        print("No new responses")
    else:
        current_invites = get_open_invites(DATA_ACCESS_TEAM_ID)
        for _, row in new_responses.iterrows():
            log_msg = validate_response(row, current_invites)
            add_result_to_logs(
                logs_wks, row["Timestamp"], row["Synapse Username"], log_msg
            )


if __name__ == "__main__":
    syn = synapseclient.Synapse()
    syn.login(silent=True)

    main()
