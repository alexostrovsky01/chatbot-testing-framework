import argparse
import logging
import sys
import os
from datetime import datetime
import shutil

# --- NOTE the relative import ---
from .framework.runner import TestRunner
from .framework.config import load_config

# --- Configure Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

def init_project(args):
    """Creates a new test project directory with default config files."""
    project_path = args.path
    logger.info(f"Initializing new test project at: {project_path}")
    
    if os.path.exists(project_path):
        print(f"Error: Directory '{project_path}' already exists.", file=sys.stderr)
        sys.exit(1)

    # The source for our default files is inside the installed package
    source_dir = os.path.join(os.path.dirname(__file__), 'default_configs')
    
    # Create the user's config directory
    user_config_path = os.path.join(project_path, 'configs')
    os.makedirs(user_config_path)

    # Copy the config files
    shutil.copy(os.path.join(source_dir, 'test_config.yaml'), user_config_path)
    shutil.copy(os.path.join(source_dir, 'prompts.py'), user_config_path)
    
    # Create other necessary directories
    os.makedirs(os.path.join(project_path, 'data'))
    os.makedirs(os.path.join(project_path, 'results'))

    # Create a placeholder data file
    with open(os.path.join(project_path, 'data', 'test_questions.csv'), 'w') as f:
        f.write("model_question,model_answer\n")
        f.write('"How much is my last bill?","Your last bill was $50."\n')

    print(f"\nProject '{project_path}' created successfully!")
    print("Next steps:")
    print(f"1. `cd {project_path}`")
    print("2. Edit `configs/test_config.yaml` to point to your chatbot's API.")
    print("3. Edit `configs/prompts.py` to add your custom evaluation policies.")
    print("4. Add your questions to `data/questions.csv`.")
    print("5. Run `chatbot-tester run --full-run` to start testing.")

def run_tests(args):
    """Loads config and executes the TestRunner."""
    try:
        config = load_config(args.config)
        logger.info(f"Successfully loaded configuration from {args.config}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}", exc_info=True)
        sys.exit(1)

    run_phase1 = args.phase1 or args.full_run
    run_phase2 = args.phase2 or args.full_run
    run_phase3 = args.phase3 or args.full_run

    if not any([run_phase1, run_phase2, run_phase3]):
        logger.error("No test phase selected. Use --phase1, --phase2, --phase3, or --full-run.")
        sys.exit(1)

    runner = TestRunner(config, args.run_id)

    if run_phase1:
        logger.info(f"--- Starting Phase 1 for Run ID: {args.run_id} ---")
        runner.run_phase1_send_questions()
        logger.info("--- Phase 1 Completed ---")
        if run_phase2 or run_phase3:
            logger.warning("Pausing for 60 seconds before continuing...")
            import time
            time.sleep(60)

    if run_phase2:
        logger.info(f"--- Starting Phase 2 for Run ID: {args.run_id} ---")
        runner.run_phase2_evaluate_performance()
        logger.info("--- Phase 2 Completed ---")

    if run_phase3:
        logger.info(f"--- Starting Phase 3 for Run ID: {args.run_id} ---")
        runner.run_phase3_evaluate_latency()
        logger.info("--- Phase 3 Completed ---")

def main():
    """Main function to parse arguments and delegate to sub-commands."""
    parser = argparse.ArgumentParser(
        description="A generic testing framework for chatbot applications."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- `init` command ---
    parser_init = subparsers.add_parser("init", help="Create a new test project structure.")
    parser_init.add_argument("path", help="The path where the new project will be created.")
    parser_init.set_defaults(func=init_project)

    # --- `run` command ---
    parser_run = subparsers.add_parser("run", help="Run the test phases.")
    parser_run.add_argument('--config', type=str, default='configs/test_config.yaml', help='Path to the config file.')
    parser_run.add_argument('--phase1', action='store_true', help="Run Phase 1: Send questions.")
    parser_run.add_argument('--phase2', action='store_true', help="Run Phase 2: Performance evaluation.")
    parser_run.add_argument('--phase3', action='store_true', help="Run Phase 3: Latency analysis.")
    parser_run.add_argument('--full-run', action='store_true', help="Execute all phases sequentially.")
    parser_run.add_argument('--run-id', type=str, default=f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}", help="A unique ID for this test run.")
    parser_run.set_defaults(func=run_tests)

    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()