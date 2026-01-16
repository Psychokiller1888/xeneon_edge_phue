# xeneon_edge_phue
Custom Philips Huee widget for Corsair Xeneon Edge

Make sure to install Python on your computer. Install Python Flask and requests as well.

The Python proxy needs to run on your computer for the widget to work.

Place the files in the "widgets" directory in your iCue install directory, usually under "C:\Program Files\Corsair\Corsair iCUE5 Software\widgets\"

Make sure to have admin rights on that widgets directory, as the python service will need to write a json file for some settings. You can choose to run the python service at another location if you do not wish to change the directory permissions.

Once the files are copied, restart iCue software. Add the widget to your Xeneon Edge. Fill in the Philips Hue bridge ip, and use the default 5057 port for proxy port setting.