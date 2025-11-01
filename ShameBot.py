# Import Python packages
import sys                              #Import sys for system calls
import os                               #Import os to get directory information
import json                             #Import json for reading and writing JSON data structures
import yaml                             #Import yaml for reading and writing YAML data structures
import requests                         #Import requests for HTTP(S) protocols
import xmltodict                        #Import xmltodict to parse XML responses to JSON
import logging                          #Import logging to send output to a log file
import ssl
import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

#Global Variables
DIRECTORY_PATH = os.path.dirname(os.path.realpath(__file__))
TOKEN_PATH = DIRECTORY_PATH + '/tokenData.conf'

# Load configuration file
with open(f"{DIRECTORY_PATH}/config.yaml", 'r') as file:
    config = yaml.safe_load(file)

def main():
    # Main function of the application

    logging.info("Starting Yahoo Fantasy Shame Bot...")
    # Initialize variables
    message = ['ShameBot says:']
    rosters = []
    hasToken = False
    shame_bool = False

    # Check to see if the token data file is present
    if 'YAHOO_TOKEN' in os.environ:
        try:
            oauth = json.loads(os.environ['YAHOO_TOKEN'])
            with open(TOKEN_PATH, 'w') as file:
                json.dump(oauth, file)
        except Exception as e:
            raise e
        hasToken = True

    try:
        logging.debug(f"Token Path: {TOKEN_PATH}")
        with open(TOKEN_PATH, 'r') as file:
            hasToken = True
    except IOError as e:
        if "No such file or directory" in e.strerror:
            hasToken = False
        else:
            logging.error(f"IO ERROR: [{e.errno}] {e.strerror}")
            sys.exit(1)
    except Exception as e:
        logging.error(f"ERROR: [{e.errno}] {e.strerror}")
        sys.exit(1)

    # Get authorization token
    if hasToken == False:
        logging.info("Token file not present. Beginning authorization process...:")
        oauth = get_full_authorization()

    # Get game key
    logging.info("Getting game key ...")
    game_key = get_game_key()

    # Retrieve league settings and save at index 0 in leagueData
    logging.info("Getting league settings...")
    leagueData = [get_league_settings(game_key)]

    # Retrieve team data and save at associated index in leagueData
    logging.info("Getting team rosters...")
    i = 1
    teamCount = int(leagueData[0]['fantasy_content']['league']['num_teams'])
    while i <= teamCount:
        teamData = get_roster(str(i), game_key)
        leagueData.insert(i, teamData)
        i += 1

    # Output leagueData to leagueData.json file
    logging.info("Saving league data to file...")
    with open('LeagueData.json', 'w') as outfile:
        json.dump(leagueData, outfile, ensure_ascii=False)

    # Extract roster data
    i = 1
    teamCount = int(leagueData[0]['fantasy_content']['league']['num_teams'])
    while i <= teamCount:
        teamName = leagueData[i]['fantasy_content']['team']['name']
        rosters.append({'team_name' : teamName, 'players' : []})
        players = leagueData[i]['fantasy_content']['team']['roster']['players']['player']
        for player in players:
            rosters[i-1]['players'].append({'name' : player['name']['full'],
                'primary_position' : player['display_position'],
                'selected_position' : player['selected_position']['position']})
        i += 1

    # Check position counts for each team
    logging.info("Checking position counts...")
    message.append(f"({leagueData[0]['fantasy_content']['league']['name']})")
    for team in rosters:
        teamCount = {
            'QB' : 0,
            'RB' : 0,
            'WR' : 0,
            'TE' : 0,
            'K' : 0,
            'DEF' : 0
            }
        for player in team['players']:
            if player['selected_position'] != "IR":
                match player['primary_position']:
                    case "QB": teamCount['QB'] += 1
                    case "RB": teamCount['RB'] += 1
                    case "WR": teamCount['WR'] += 1
                    case "TE": teamCount['TE'] += 1
                    case "K": teamCount['K'] += 1
                    case "DEF": teamCount['DEF'] += 1

        for position in teamCount:
            if teamCount[position] > config['Roster_Limits'][position]:
                message.append(f"{team['team_name']} has too many {position}s, {str(teamCount[position])} of {str(config['Roster_Limits'][position])} allowed.")
                shame_bool = True

    # Send email message
    if shame_bool:
        logging.info("Sending email message...")
        logging.info(message)
        with open(f"{DIRECTORY_PATH}/shameGIF.webp", 'rb') as filepath:
            shameGIF = MIMEImage(filepath.read())
        eMessage = MIMEMultipart()
        eMessage.attach(shameGIF)
        eMessage.attach(MIMEText("<br>".join(message), 'html'))
        eMessage['Subject'] = f"{config['Email_Settings']['subject']} - {leagueData[0]['fantasy_content']['league']['name']}"
        eMessage['From'] = config['Email_Settings']['sendereMail']
        eMessage['To'] = config['Email_Settings']['receivereMail']

        context = ssl.create_default_context()
        print(eMessage['Subject'])
        print(message)
        with smtplib.SMTP_SSL(host=config['Email_Settings']['smtpServer'], port=config['Email_Settings']['port'], context=context) as server:
            server.login(config['Email_Settings']['sendereMail'], config['Email_Settings']['password'])
            server.sendmail(config['Email_Settings']['sendereMail'], config['Email_Settings']['receivereMail'].split(","), eMessage.as_string())
    else:
        logging.info("No roster limits exceeded.")

    return;

def get_full_authorization():
    # Gets full authorization for the application to access Yahoo APIs and get User Data.
    # Writes all relevant data to tokenData.conf

    # Step 1: Get authorization from User to access their data
    authURL = f"{config['Yahoo_Settings']['REQUEST_AUTH_URL']}?client_id={config['Yahoo_Settings']['consumer_key']}&redirect_uri=oob&response_type=code"
    logging.debug(authURL)
    print (f"You need to authorize this application to access your data.\nPlease go to {authURL}")
    authorized = 'n'

    while authorized.lower() != 'y':
        authorized = input('Have you authorized me? (y/n)')
        if authorized.lower() != 'y':
            print ("You need to authorize me to continue...")

    authCode = input("What is the code? ")

    # Step 2: Get Access Token to send requests to Yahoo APIs
    response = get_access_token(authCode)
    oauth = parse_response(response)
    return oauth

def get_access_token(verifier):
    # Gets the access token used to allow access to user data within Yahoo APIs
    # Returns access token payload

    logging.info("Getting access token...")

    response = requests.post(config['Yahoo_Settings']['REQUEST_TOKEN_URL'], data = {'client_id' : config['Yahoo_Settings']['consumer_key'], 'client_secret' : config['Yahoo_Settings']['consumer_secret'], 'redirect_uri' : 'oob', 'code' : verifier, 'grant_type' : 'authorization_code'})

    if response.status_code == 200:
        logging.info("Success!")
        logging.debug(response.content)
        return response.content
    else:
        logging.error("Access Token Request returned a non 200 code")
        logging.error("---------DEBUG--------")
        logging.error(f"HTTP Code: {response.status_code}")
        logging.error(f"HTTP Response: \n{response.content}")
        logging.error("-------END DEBUG------")
        sys.exit(1)

def parse_response (response):
    # Receives the token payload and breaks it up into a dictionary and saves it to tokenData.conf
    # Returns a dictionary to be used for API calls

    parsedResponse = json.loads(response)
    accessToken = parsedResponse['access_token']
    refreshToken = parsedResponse['refresh_token']

    oauth = {}

    oauth['token'] = accessToken
    oauth['refreshToken'] = refreshToken

    try:
        with open(TOKEN_PATH, 'w') as file:
            json.dump(oauth, file)
        return oauth
    except Exception as e:
        raise e

def query_yahoo_api(url, dataType):
    # Queries the yahoo fantasy sports api

    oauth = read_oauth_token()
    header = f"Bearer {oauth['token']}"
    logging.debug(f"URL: {url}")
    response = requests.get(url, headers={'Authorization' : header})
    
    if response.status_code == 200:
        logging.debug(f"Successfully got {dataType} data")
        logging.debug(response.content)
        if dataType == "game key":
            string_response = response.content.decode('utf-8')
            payload = json.loads(string_response)
        else:
            payload = xmltodict.parse(response.content)
        logging.debug(f"Successfully parsed {dataType} data")
        return payload
    elif response.status_code == 401 and b"token_expired" in response.content:
        logging.info("Token Expired....renewing")
        oauth = refresh_access_token(oauth['refreshToken'])
        return query_yahoo_api(url, dataType)
    else:
        logging.error(f"Could not get {dataType} information")
        logging.error("---------DEBUG--------")
        logging.error(f"HTTP Code: {response.status_code}")
        logging.error(f"HTTP Response: \n{response.content}")
        logging.error("-------END DEBUG------")
        sys.exit(1)

def read_oauth_token():
    # Reads the token data from file and returns a dictionary object

    logging.debug("Reading token details from file...")

    try:
        with open(TOKEN_PATH, 'r') as file:
            oauth = json.load(file)
    except Exception as e:
        raise e

    logging.debug("Reading complete!")
    return oauth

def refresh_access_token(refreshToken):
    # Refreshes the access token as it expires every hour
    # Returns access token payload

    logging.info("Refreshing access token...")

    response = requests.post(config['Yahoo_Settings']['REQUEST_TOKEN_URL'], data = {'client_id' : config['Yahoo_Settings']['consumer_key'], 'client_secret' : config['Yahoo_Settings']['consumer_secret'], 'redirect_uri' : 'oob', 'refresh_token' : refreshToken, 'grant_type' : 'refresh_token'})

    if response.status_code == 200:
        logging.info("Success!")
        logging.debug(response.content)
        oauth = parse_response(response.content)
        return oauth
    else:
        logging.error("Access Token Request returned a non 200 code")
        logging.error("---------DEBUG--------")
        logging.error(f"HTTP Code: {response.status_code}")
        logging.error(f"HTTP Response: \n{response.content}")
        logging.error("-------END DEBUG------")
        sys.exit(1)

def get_game_key():
    # Get the game key for the current year

    gameKeyURL = f"{config['Yahoo_Settings']['BASE_YAHOO_API_URL']}games;game_codes=nfl;seasons={config['Yahoo_Settings']['current_year']}?format=json"
    yahoo_fantasy_data = query_yahoo_api(gameKeyURL, "game key")
    return yahoo_fantasy_data['fantasy_content']['games']['0']['game'][0]['game_key']

def get_league_settings(game_key):
    # Get the number of teams

    leagueSettingsURL = f"{config['Yahoo_Settings']['BASE_YAHOO_API_URL']}league/{game_key}.l.{config['Yahoo_Settings']['league_id']}/settings"
    return query_yahoo_api(leagueSettingsURL, "settings")

def get_roster(teamID, game_key):
    # Get the roster from Yahoo and parses the response

    rosterURL = f"{config['Yahoo_Settings']['BASE_YAHOO_API_URL']}team/{game_key}.l.{config['Yahoo_Settings']['league_id']}.t.{teamID}/roster"
    return query_yahoo_api(rosterURL, "roster")

# Initiate logging, set logging level (options for level=logging.**** are INFO, ERROR, or DEBUG)
logging.basicConfig(filename='FantasyShameBotLog.log', level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

main()

logging.info("Done!")
