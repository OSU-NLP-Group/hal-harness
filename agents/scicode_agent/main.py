# This is an example agent that generates code for the SciCode benchmark in a zero-shot format.

from openai import OpenAI
from datasets import load_dataset
from typing import Any
from pathlib import Path
from agent import agent

def run(input: dict[str, Any], **kwargs) -> dict[str, str]:

    assert 'model_name' in kwargs, 'model_name is required'

    def process_problem_code(prob_data: dict, num_steps: int) -> str:
        """Process problem code and return the function header and return line"""
        header_docstring = prob_data['sub_steps'][num_steps - 1]['function_header']
        return_str = prob_data['sub_steps'][num_steps - 1]['return_line']
        string = f"{header_docstring}\n\n{return_str}"
        return string

    def process_problem_steps(with_background: bool, previous_llm_code: list[str],
                              problem_data: dict, num_steps: int) -> tuple[str, str, str]:
        """Process problem data and return previous steps and next steps"""
        output_lines = []
        next_step = []
        previous_code = []
        for i in range(num_steps - 1):
            output_lines.append((problem_data["sub_steps"][i]["step_description_prompt"] + '\n' +
                                problem_data["sub_steps"][i]["step_background"]) if with_background
                                else problem_data["sub_steps"][i]["step_description_prompt"])
            output_lines.append(previous_llm_code[i])
            previous_code.append(previous_llm_code[i])
            output_lines.append("------")

        next_step.append((problem_data["sub_steps"][num_steps - 1]["step_description_prompt"] + '\n' +
                         problem_data["sub_steps"][num_steps - 1]["step_background"]) if with_background
                         else problem_data["sub_steps"][num_steps - 1]["step_description_prompt"])
        next_step.append(process_problem_code(problem_data, num_steps))
        output_str = "\n\n".join(output_lines[:-1])  # Remove the last "------"
        next_step_str = "\n\n".join(next_step)
        previous_code_str = "\n".join(previous_code)
        return output_str, next_step_str, previous_code_str
    
    def generate_prompt_with_steps(with_background: bool, previous_llm_code: list[str],
                                   prob_data: dict, num_steps: int, prompt_template: str) -> tuple[str, str]:
        """Generate prompt with steps for scicode and scicode easy benchmark"""
        # Parse the input file and extract the content
        problem_steps_str, next_step_str, previous_code_str = process_problem_steps(with_background, previous_llm_code, prob_data,
                                                                                         num_steps)
        dependencies = prob_data["required_dependencies"]
        assert next_step_str
        return prompt_template.format(
            problem_steps_str=problem_steps_str,
            next_step_str=next_step_str,
            dependencies=dependencies,
        ), f'{dependencies}\n'
    
    def generate_prompt_without_steps(prob_data: dict, prompt_template: str):
        """Generate prompt without steps for scicode_hard benchmark"""
        output_lines = []
        for i in range(len(prob_data["sub_steps"])):
            output_lines.append(prob_data["sub_steps"][i]["step_description_prompt"])
            output_lines.append(process_problem_code(prob_data, i))
            output_lines.append("------")
        output_str = "\n\n".join(output_lines[:-1]) 
    
        dependencies = prob_data["required_dependencies"]

        return prompt_template.format(
            next_step_str=output_str,
            dependencies=dependencies,
        ), f'{dependencies}\n'

    # Get the benchmark name from kwargs
    benchmark_name = kwargs['benchmark_name']
    
    client = OpenAI()

    # Initialize results dictionary
    results = {}

    # Load the prompt template based on the benchmark name
    if benchmark_name == 'scicode_hard':
        prompt_template = Path("hard_prompt_template.txt").read_text()
    elif benchmark_name == 'scicode_easy':
        prompt_template = Path("easy_prompt_template.txt").read_text()
    else:
        prompt_template = Path("prompt_template.txt").read_text()

    # For the hard benchmark, generate full prompt once for each problem
    if benchmark_name == 'scicode_hard':
        for task_id, task in input.items():
            print(f'Generating {task_id}...')

            prompt, dependencies = generate_prompt_without_steps(
                prob_data=task,
                prompt_template=prompt_template
            )

            response = agent.run(prompt)
            
            generated_code = response.choices[0].message.content
            generated_code = generated_code.replace("```python", "").replace("```", "").strip()

            results[task_id] = generated_code

    # For the easy and standard benchmarks, generate full prompt for each subtask
    else:

        # Determine if the benchmark is easy to add background information
        easy = True if benchmark_name == 'scicode_easy' else False

        # Iterate through problems
        for task_id, task in input.items():
            if task_id != "11":
                continue
            previous_llm_code = ""
            steps = len(task['sub_steps'])
            print(f'Generating {task_id}...')
            steps_results = {}

            for i in range(steps):
                prompt, dependencies = generate_prompt_with_steps(
                    with_background=easy,
                    previous_llm_code=previous_llm_code,
                    prob_data=task,
                    num_steps=i + 1,
                    prompt_template=prompt_template
                )

                response = client.chat.completions.create(
                    model=kwargs['model_name'],
                    messages=[{"role": "user", "content": prompt}],
                    n=1,
                    temperature=0,
                )

                generated_code = response.choices[0].message.content

                # Remove the ```python and final ``` from generated_code
                generated_code = generated_code.replace("```python", "").replace("```", "").strip()

                # Update previous_llm_code string with the generated code
                previous_llm_code += f'\n{generated_code}'

                # Store the generated code for the current step
                if easy == True:
                    steps_results[f'{task_id}.{i + 1}'] = previous_llm_code
                else:
                    steps_results[f'{task_id}.{i + 1}'] = dependencies + previous_llm_code
                
            results[task_id] = steps_results
        
    return results