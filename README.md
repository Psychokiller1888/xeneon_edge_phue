# xeneon_edge_phue
Custom Philips Hue widget for Corsair Xeneon Edge

Make sure to install Python on your computer: https://www.python.org/downloads/

Place the files in the "widgets" directory in your iCue install directory, usually under "C:\Program Files\Corsair\Corsair iCUE5 Software\widgets\".

Make sure to have admin rights on the iCue widgets directory, as the python service will need to write a json file for some settings. You can choose to place and run the python service at any other location if you do not wish to change the directory permissions, as the script is only a proxy and not used by iCue directly.

Install Python Flask and requests as well:

- In the modules directory, open a console
- Create a virtual environement by typing: `python -m  venv venv`
- Activate the virtual environement: `venv\Scripts\activate`
- Install Flask: `pip install flask`
- Install Requests: `pip install requests`

The Python proxy needs to run on your computer for the widget to work. In the same console, type:

`venv\Scripts\python.exe hueLocalService.py`

Restart iCue software. Add the widget to your Xeneon Edge. Fill in the Philips Hue bridge ip, and use the default 5057 port for proxy port setting. Press the bridge button to create a new user
