# bradipo

`bradipo` è uno script per scaricare i registri da [Portale Antenati](https://antenati.cultura.gov.it).  Il download avviene attraverso un manifest dichiarato a livello di pagina e non ricostruendo l'immagine dai tasselli.  Ciò permette un download più veloce, ma probabilmente una minore granularità nella selezione della risoluzione.

Per come è impostato ora, lo script utilizza [`uv`](https://github.com/astral-sh/uv) ed è sufficiente un `chmod +x bradipo.py` per avviarlo.  In alternativa, si può usare un [virtual environment](https://docs.python.org/3/library/venv.html).
