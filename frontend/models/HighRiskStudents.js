const { DataTypes } = require('sequelize');
const sequelize = require('../config/database');
const Student = require('./Student');
const Advisor = require('./Advisor');

const HighRiskStudents = sequelize.define('High_Risk_Student', {
  student_id: {
    type: DataTypes.INTEGER,
    primaryKey: true,
    references: {
      model: Student,
      key: 'student_id'
    },
    onDelete: 'CASCADE'
  },
  student_name: {
    type: DataTypes.STRING(61),
    allowNull: false
  },
  cumulative_gpa: {
    type: DataTypes.FLOAT,
    allowNull: false,
    validate: {
      max: 2.0
    }
  },
  advisor_id: {
    type: DataTypes.STRING(50),
    allowNull: false,
    references: {
      model: Advisor,
      key: 'advisor_id'
    },
    onDelete: 'RESTRICT'
  }
}, {
  tableName: 'High_Risk_Student',
  timestamps: false
});

// Associations
HighRiskStudents.belongsTo(Student, {
  foreignKey: 'student_id',
  onDelete: 'CASCADE'
});

HighRiskStudents.belongsTo(Advisor, {
  foreignKey: 'advisor_id',
  onDelete: 'RESTRICT'
});

module.exports = HighRiskStudents;
