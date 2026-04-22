import unittest
from masker import PIIMasker

class TestPIIMasker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Inizializza il masker una sola volta per tutti i test (risparmia tempo di caricamento del modello NLP)
        print("Inizializzazione modello spaCy in corso...")
        cls.masker = PIIMasker()
        print("Modello pronto. Avvio test di Governance.\n")

    def test_01_deterministico_regex(self):
        """Verifica che email, telefoni e CF vengano mascherati correttamente."""
        self.assertEqual(self.masker.mask("Scrivi a mario.rossi@email.it"), "Scrivi a [EMAIL]")
        self.assertEqual(self.masker.mask("Chiama il +39 333 1234567"), "Chiama il [PHONE]")
        self.assertEqual(self.masker.mask("CF: RSSMRA80A01H501W"), "CF: [FISCAL_CODE]")

    def test_02_probabilistico_nlp(self):
        """Verifica che i nomi propri di persona vengano mascherati."""
        self.assertEqual(self.masker.mask("Ho parlato con Mario Rossi ieri."), "Ho parlato con [PERSON] ieri.")
        self.assertEqual(self.masker.mask("L'avv. Giuseppe Bianchi ha chiamato."), "L'avv. [PERSON] ha chiamato.")

    def test_03_negative_controls_business_value(self):
        """VERIFICA DI GOVERNANCE: Luoghi e Organizzazioni NON devono essere mascherati."""
        self.assertEqual(self.masker.mask("L'azienda Verdi S.p.A. ha sede a Milano."), "L'azienda Verdi S.p.A. ha sede a Milano.")
        self.assertEqual(self.masker.mask("Comune di Roma: tel +39 06 0606"), "Comune di Roma: tel [PHONE]")
        self.assertEqual(self.masker.mask("Via Giuseppe Verdi 10, Milano"), "Via [PERSON] 10, Milano")

    def test_04_protezione_timestamp(self):
        """Verifica che i log temporali non vengano distrutti o confusi per telefoni."""
        self.assertEqual(
            self.masker.mask("[2026-04-21 10:22] Chiamata da Mario al 3331234567"), 
            "[2026-04-21 10:22] Chiamata da [PERSON] al [PHONE]"
        )

if __name__ == '__main__':
    unittest.main(verbosity=2)