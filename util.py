def yes_or_no(prompt):
    while True:
        reply = str(input(f'{prompt} (y/n): ')).lower().strip()
        if len(reply) > 0:
            if reply[0] == 'y':
                return True
            if reply[0] == 'n':
                return False
