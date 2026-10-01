"""Testes do carregamento de chaves (.env).

O ponto central: "eu pus tudo certinho" precisa funcionar mesmo sem o pacote
python-dotenv instalado, e qualquer problema tem que aparecer no --check.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from main import describe_env  # noqa: E402
from providers import load_env, mask_secret, parse_env_file  # noqa: E402


class ParseEnvFileTests(unittest.TestCase):
    def escrever(self, conteudo, nome=".env"):
        pasta = tempfile.mkdtemp()
        caminho = os.path.join(pasta, nome)
        with open(caminho, "w", encoding="utf-8") as handle:
            handle.write(conteudo)
        return caminho

    def test_le_chaves_simples(self):
        caminho = self.escrever("APINEX_API_KEY=sk-apx_123\nTWITCH_OAUTH=oauth:abc\n")
        dados = parse_env_file(caminho)
        self.assertEqual(dados["APINEX_API_KEY"], "sk-apx_123")
        self.assertEqual(dados["TWITCH_OAUTH"], "oauth:abc")

    def test_ignora_comentarios_linhas_vazias_e_espacos(self):
        caminho = self.escrever(
            "# comentario\n\n  APINEX_API_KEY  =  sk-apx_123  \nnao-e-chave\n")
        self.assertEqual(parse_env_file(caminho), {"APINEX_API_KEY": "sk-apx_123"})

    def test_aceita_export_e_aspas(self):
        caminho = self.escrever('export TWITCH_OAUTH="oauth:aspas"\nX=\'simples\'\n')
        dados = parse_env_file(caminho)
        self.assertEqual(dados["TWITCH_OAUTH"], "oauth:aspas")
        self.assertEqual(dados["X"], "simples")

    def test_aceita_arquivo_do_windows_com_bom_e_crlf(self):
        pasta = tempfile.mkdtemp()
        caminho = os.path.join(pasta, ".env")
        with open(caminho, "wb") as handle:
            handle.write("\ufeffAPINEX_API_KEY=sk-apx_bom\r\nTWITCH_OAUTH=oauth:x\r\n".encode("utf-8"))
        dados = parse_env_file(caminho)
        self.assertEqual(dados["APINEX_API_KEY"], "sk-apx_bom")
        self.assertEqual(dados["TWITCH_OAUTH"], "oauth:x")

    def test_arquivo_inexistente_nao_quebra(self):
        self.assertEqual(parse_env_file("/caminho/que/nao/existe/.env"), {})


class LoadEnvTests(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.caminho = os.path.join(self.pasta, ".env")
        self.salvo = dict(os.environ)
        self._dotenv_salvo = sys.modules.get("dotenv", "ausente")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.salvo)
        if self._dotenv_salvo == "ausente":
            sys.modules.pop("dotenv", None)
        else:
            sys.modules["dotenv"] = self._dotenv_salvo

    def escrever(self, conteudo):
        with open(self.caminho, "w", encoding="utf-8") as handle:
            handle.write(conteudo)

    def test_carrega_chaves_do_env(self):
        self.escrever("APINEX_API_KEY=sk-apx_do_env\nTWITCH_OAUTH=oauth:do_env\n")
        report = load_env(self.caminho)
        self.assertTrue(report["found"])
        self.assertEqual(os.environ["APINEX_API_KEY"], "sk-apx_do_env")
        self.assertEqual(os.environ["TWITCH_OAUTH"], "oauth:do_env")
        self.assertIn("APINEX_API_KEY", report["keys"])

    def test_funciona_como_leitor_interno_sem_python_dotenv(self):
        """Este era o bug: sem o pacote, o .env era ignorado em silencio."""
        sys.modules["dotenv"] = None  # faz "import dotenv" falhar
        self.escrever("APINEX_API_KEY=sk-apx_sem_dotenv\n")
        report = load_env(self.caminho)
        self.assertEqual(os.environ.get("APINEX_API_KEY"), "sk-apx_sem_dotenv")
        self.assertFalse(report["dotenv"])
        self.assertTrue(any("python-dotenv" in aviso for aviso in report["warnings"]))

    def test_nao_sobrescreve_variavel_ja_definida_no_sistema(self):
        os.environ["APINEX_API_KEY"] = "sk-apx_do_sistema"
        self.escrever("APINEX_API_KEY=sk-apx_do_arquivo\n")
        report = load_env(self.caminho)
        self.assertEqual(os.environ["APINEX_API_KEY"], "sk-apx_do_sistema")
        self.assertEqual(report["sources"]["APINEX_API_KEY"], "ambiente")

    def test_avisa_quando_o_arquivo_tem_nome_errado(self):
        pasta = tempfile.mkdtemp()
        with open(os.path.join(pasta, ".env.txt"), "w", encoding="utf-8") as handle:
            handle.write("APINEX_API_KEY=sk-apx_txt\n")
        cwd = os.getcwd()
        os.chdir(pasta)
        try:
            report = load_env()
        finally:
            os.chdir(cwd)
        self.assertFalse(report["found"])
        self.assertTrue(any(".env.txt" in aviso for aviso in report["warnings"]))

    def test_avisa_quando_a_chave_ainda_e_o_exemplo(self):
        self.escrever("APINEX_API_KEY=sk-apx_coloque_sua_key_aqui\n")
        report = load_env(self.caminho)
        self.assertTrue(any("exemplo" in aviso for aviso in report["warnings"]))

    def test_avisa_erro_de_digitacao_no_nome_da_variavel(self):
        self.escrever("APINEX_API=sk-apx_errado\n")
        report = load_env(self.caminho)
        self.assertTrue(any("quis dizer APINEX_API_KEY" in aviso
                            for aviso in report["warnings"]))

    def test_mask_secret_esconde_o_miolo(self):
        self.assertEqual(mask_secret("sk-apx_1234567890abc"), "sk-apx...0abc")
        self.assertEqual(mask_secret("oauth:valido"), "oauth:...lido")
        self.assertEqual(mask_secret(""), "(vazia)")
        self.assertNotIn("67890", mask_secret("sk-apx_1234567890abc"))
        self.assertLess(len(mask_secret("a" * 60)), 20)


class DescribeEnvTests(unittest.TestCase):
    """O --check tem que mostrar de onde veio cada chave."""

    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.cwd = os.getcwd()
        self.salvo = dict(os.environ)
        os.chdir(self.pasta)

    def tearDown(self):
        os.chdir(self.cwd)
        os.environ.clear()
        os.environ.update(self.salvo)

    def test_mostra_que_a_chave_veio_do_env(self):
        with open(os.path.join(self.pasta, ".env"), "w", encoding="utf-8") as handle:
            handle.write("APINEX_API_KEY=sk-apx_teste_123456\nTWITCH_OAUTH=oauth:token_9999\n")
        linhas = []
        describe_env({"provider": "apinex"}, linhas.append)
        texto = "\n".join(linhas)
        self.assertIn("encontrado", texto)
        self.assertIn("via .env", texto)
        self.assertIn("sk-apx...3456", texto)        # miolo escondido
        self.assertNotIn("sk-apx_teste_123456", texto)

    def test_avisa_quando_nao_acha_o_env(self):
        linhas = []
        describe_env({"provider": "apinex"}, linhas.append)
        texto = "\n".join(linhas)
        self.assertIn("NAO ENCONTRADO", texto)
        self.assertIn("NAO DEFINIDA", texto)
        self.assertIn(".env.example", texto)

    def test_reconhece_token_no_proprio_config(self):
        linhas = []
        describe_env({"provider": "apinex", "api_key": "sk-apx_no_config",
                      "twitch": {"oauth": "oauth:no_config"}}, linhas.append)
        texto = "\n".join(linhas)
        self.assertIn("config.json", texto)


if __name__ == "__main__":
    unittest.main()


class PastaErradaTests(unittest.TestCase):
    """Quem cria o .env na pasta errada precisa de uma pista, nao de silencio."""

    def test_acha_env_na_raiz_acima_do_projeto(self):
        import shutil
        import subprocess

        raiz = tempfile.mkdtemp()
        projeto = os.path.join(raiz, "ai-vs-streamer-v5")
        shutil.copytree(os.path.join(BASE_DIR, "providers"),
                        os.path.join(projeto, "providers"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        with open(os.path.join(raiz, ".env"), "w", encoding="utf-8") as handle:
            handle.write("APINEX_API_KEY=sk-apx_na_raiz_9999\n")

        codigo = ("import os, sys; sys.path.insert(0, '.');"
                  " from providers import load_env;"
                  " r = load_env();"
                  " print(r['found'], r['path'], os.environ.get('APINEX_API_KEY'))")
        saida = subprocess.run([sys.executable, "-c", codigo], cwd=projeto,
                               capture_output=True, text=True, timeout=60).stdout
        self.assertIn("True", saida)
        self.assertIn("sk-apx_na_raiz_9999", saida)

    def test_avisa_onde_procurou_quando_nao_acha(self):
        raiz = tempfile.mkdtemp()
        report = load_env(os.path.join(raiz, ".env"))
        self.assertFalse(report["found"])
        aviso = report["warnings"][0]
        self.assertIn("nao achei o arquivo .env", aviso)
        self.assertIn(".env", aviso)
