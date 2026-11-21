"""Mesa virtual do Long Journey: deckbuilder e emulador de partida.

Uso: python mesa.py [--porta 8766] [--rede] [--sem-navegador]
  --rede   aceita jogadores de outros computadores da mesma rede (mostra o endereço)

As cartas vêm de cards/: cada carta salva (no criador, app.py, ou à mão) entra sozinha no
acervo da mesa em poucos segundos, e as páginas abertas atualizam na hora.
"""

from mesa.servidor import main

if __name__ == "__main__":
    main()
