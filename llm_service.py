import os
import time
from openai import OpenAI
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

class LLMService:
    def __init__(self):
        """Inicializa o cliente OpenAI configurado para DeepSeek"""
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY não encontrada no arquivo .env")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url="https://api.deepseek.com",
            timeout=30.0,  # 30s — evita workers travados em falhas de rede
        )

        self.model = "deepseek-chat"
        self.max_retries = 3
    
    def generate_answer(self, context, question, max_tokens=3000):
        """
        Gera uma resposta baseada no contexto fornecido
        
        Args:
            context: Lista de dicionários com textos relevantes do PDF
            question: Pergunta do usuário
            max_tokens: Número máximo de tokens na resposta
        
        Returns:
            Resposta gerada pela IA
        """
        # Preparar o contexto formatado com metadados para citação
        context_items = []
        for i, result in enumerate(context):
            # Fallback: Se não houver seguradora, usa o nome do arquivo (sem o caminho completo)
            seguradora = result.get('seguradora')
            if not seguradora or seguradora == 'Desconhecida':
                source_path = result.get('source', 'Documento')
                seguradora = os.path.basename(source_path).replace('.pdf', '')
                
            pagina = result.get('page', 'N/A')
            item = (
                f"[Trecho {i+1} - Fonte: {seguradora} | Pág. {pagina}]:\n"
                f"{result['text']}"
            )
            context_items.append(item)
            
        context_text = "\n\n".join(context_items)
        
        # Montar o prompt do sistema
        system_prompt = """Você é o AUDITOR IA DE SINISTROS - um especialista forense em apólices de seguros.
        Sua missão é encontrar detalhes técnicos que passam despercebidos por leituras superficiais.

        COMPORTAMENTO INVESTIGATIVO:
        - Se o usuário perguntar sobre um serviço específico (ex: "Encanador", "Chaveiro"), VASCULHE as tabelas de Assistência 24h, Coberturas Adicionais e Serviços Inclusos.
        - Regras específicas SEMPRE sobrepõem regras gerais. Se encontrar uma exceção ou condição particular, ela tem precedência.
        - Valores em R$, limites de utilização e carências devem ser DESTACADOS com ênfase.
        - Se houver conflito aparente entre trechos, apresente AMBOS com suas respectivas páginas.

        FORMATO DE RESPOSTA OBRIGATÓRIO:
        Estruture TODA resposta neste template de 4 seções:

        **1. VEREDITO DIRETO:**
        [Resposta objetiva em 1-2 frases]

        **2. DETALHES TÉCNICOS:**
        - Limites de cobertura/utilização
        - Valores (R$)
        - Carências e prazos
        - Condições de acionamento

        **3. A "LETRA MIÚDA":**
        [Regras específicas, exceções, restrições ou observações importantes que podem passar despercebidas]

        **4. PROVA DOCUMENTAL:**
        [Seguradora | Pág. X] para cada afirmação feita acima

        REGRAS CRÍTICAS:
        - NUNCA diga "não encontrei" sem antes vasculhar TODOS os trechos fornecidos
        - Se a informação realmente não existir, sugira onde ela DEVERIA estar (ex: "Verifique a seção de Assistências na apólice completa")
        - Seja extremamente rigoroso com números e datas
        
        CONTEXTO DO DOCUMENTO:
        {context}
        """
        
        # Montar a mensagem do usuário
        user_message = f"""Pergunta: {question}

INSTRUÇÕES DE ANÁLISE:
- Investigue o contexto como um auditor de sinistros
- Priorize tabelas e listas de limites se a pergunta envolver valores ou serviços
- Use o formato de resposta estruturado (4 seções)
- Cite TODAS as fontes no formato [Seguradora | Pág. X]"""
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt.format(context=context_text)},
                        {"role": "user", "content": user_message}
                    ],
                    max_tokens=max_tokens,
                    temperature=0.3,  # Baixa temperatura para respostas mais consistentes
                    stream=False
                )
                return response.choices[0].message.content

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait = 2 ** attempt  # backoff: 1s, 2s
                    print(f"Tentativa {attempt + 1} falhou ({e}). Aguardando {wait}s antes de tentar novamente...")
                    time.sleep(wait)

        print(f"Todas as {self.max_retries} tentativas falharam: {last_error}")
        return f"Desculpe, não foi possível obter resposta após {self.max_retries} tentativas. Tente novamente em instantes."
    
    def test_connection(self):
        """Testa a conexão com a API da DeepSeek"""
        try:
            self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": "Responda apenas com 'OK' se estiver funcionando."}],
                max_tokens=10
            )
            return True, "Conexão com DeepSeek API estabelecida com sucesso!"
        except Exception as e:
            return False, f"Erro na conexão: {str(e)}"

# Função de conveniência
def create_llm_service():
    return LLMService()

if __name__ == "__main__":
    # Teste rápido
    try:
        llm = LLMService()
        success, message = llm.test_connection()
        print(message)
        
        if success:
            # Teste com contexto de exemplo
            test_context = [
                {
                    "text": "O seguro de equipamentos agrícolas cobre danos por incêndio, raio e explosão. A franquia é de R$ 1.000,00 por ocorrência.",
                    "relevance_score": 0.95,
                    "source": "test.pdf",
                    "chunk_index": 0
                }
            ]
            test_question = "Qual é o valor da franquia?"
            answer = llm.generate_answer(test_context, test_question)
            print(f"\nTeste de resposta:\nPergunta: {test_question}\nResposta: {answer}")
    except ValueError as e:
        print(f"Erro de configuração: {e}")