class user:
    def __init__(self, sex, height, age, weight, activity_level):
        if sex not in ["male", "female"]:
            raise NameError("Sex must be 'male' or 'female'.")
        self.sex = sex
        
        self.height = height
        self.age = age  
        self.weight = weight
        
        valid_activity_levels = ["sedentary", "lightly active", "moderately active", "very active", "extra active"]
        if activity_level not in valid_activity_levels:
            raise NameError(f"Activity level must be one of: {', '.join(valid_activity_levels)}.")
        self.activity_level = activity_level

    def get_bmr(self):
        if self.sex == "male":
            base_bmr =  10 * self.weight + 6.25 * self.height - 5 * self.age + 5
        elif self.sex == "female":
            base_bmr =  10 * self.weight + 6.25 * self.height - 5 * self.age - 161
        
        if self.activity_level == "sedentary":
            return base_bmr * 1.2
        elif self.activity_level == "lightly active":
            return base_bmr * 1.375
        elif self.activity_level == "moderately active":
            return base_bmr * 1.55
        elif self.activity_level == "very active":
            return base_bmr * 1.725
        elif self.activity_level == "extra active":
            return base_bmr * 1.9
    def goal_based_bmr(self, goal):
        tdee = self.get_bmr() # Get the TDEE (Total Daily Energy Expenditure)

        valid_goals = ["Fat Loss", "Lean Gains", "General Health / Maintenance", "Build Muscle"]
        if goal not in valid_goals:
            raise NameError(f"Goal must be one of: {', '.join(valid_goals)}.")

        if goal == "Fat Loss":
            return tdee * 0.80
        elif goal == "Lean Gains":
            return tdee * 0.90
        elif goal == "General Health / Maintenance":
            return tdee * 1.00
        elif goal == "Build Muscle":
            return tdee * 1.10
    def protein_intake(self, goal):
        valid_goals = ["Fat Loss", "Lean Gains", "General Health / Maintenance", "Build Muscle"]
        if goal not in valid_goals:
            raise NameError(f"Goal must be one of: {', '.join(valid_goals)}.")

        if goal == "Fat Loss":
            height_in_meters = self.height / 100 
            return 23 * (height_in_meters ** 2) * 2.0
        elif goal == "Lean Gains":
            return 2.2 * self.weight
        elif goal == "Build Muscle":
            return 2.2 * self.weight
        elif goal == "General Health / Maintenance":
            return 1.6 * self.weight

    def fat_intake(self, goal):
        valid_goals = ["Fat Loss", "Lean Gains", "General Health / Maintenance", "Build Muscle"]
        if goal not in valid_goals:
            raise NameError(f"Goal must be one of: {', '.join(valid_goals)}.")
            
        total_goal_calories = self.goal_based_bmr(goal)
        
        return (total_goal_calories * 0.25) / 9

    def carbs_intake(self, goal):
        valid_goals = ["Fat Loss", "Lean Gains", "General Health / Maintenance", "Build Muscle"]
        if goal not in valid_goals:
            raise NameError(f"Goal must be one of: {', '.join(valid_goals)}.")

        total_calories = self.goal_based_bmr(goal)
        
        protein_grams = self.protein_intake(goal)
        protein_calories = protein_grams * 4
        
        fat_grams = self.fat_intake(goal)
        fat_calories = fat_grams * 9
        
        remaining_calories = total_calories - protein_calories - fat_calories
        
        return remaining_calories / 4


Miguel = user("male",180,26,86,"moderately active")
print("BMR:", Miguel.get_bmr())
print("Goal-based BMR (Build Muscle):", Miguel.goal_based_bmr("Lean Gains"))
print("Protein Intake (Build Muscle):", Miguel.protein_intake("Lean Gains"))
print("Fat Intake (Build Muscle):", Miguel.fat_intake("Lean Gains"))
print("Carbs Intake (Build Muscle):", Miguel.carbs_intake("Lean Gains"))