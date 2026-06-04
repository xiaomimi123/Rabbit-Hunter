
import React from 'react';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, ResponsiveContainer, PieChart, Pie, Cell, Tooltip } from 'recharts';
import { COLORS } from '../constants';

export const AIWeightRadar: React.FC<{ weights: any }> = ({ weights }) => {
  const data = [
    { subject: 'Structure', A: weights.structure, fullMark: 100 },
    { subject: 'Sentiment', A: weights.sentiment, fullMark: 100 },
    { subject: 'Volatility', A: weights.volatility, fullMark: 100 },
    { subject: 'Manipulation', A: weights.manipulation, fullMark: 100 },
    { subject: 'Gap', A: 60, fullMark: 100 },
  ];

  return (
    <div className="w-full h-full min-h-[220px] min-w-0" style={{ width: '100%', height: '100%', minHeight: '220px' }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={220} aspect={undefined}>
        <RadarChart cx="50%" cy="50%" outerRadius="60%" data={data}>
          <PolarGrid stroke="#ffffff10" />
          <PolarAngleAxis dataKey="subject" tick={{ fill: '#ffffff50', fontSize: 10, fontFamily: 'JetBrains Mono' }} />
          <Radar
            name="AI Priority"
            dataKey="A"
            stroke={COLORS.ai}
            fill={COLORS.ai}
            fillOpacity={0.4}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
};

export const HealthDonut: React.FC = () => {
  const data = [
    { name: 'Active', value: 80 },
    { name: 'Idle', value: 20 },
  ];
  return (
    <div className="w-full h-full min-h-[200px] min-w-0" style={{ width: '100%', height: '100%', minHeight: '200px' }}>
      <ResponsiveContainer width="100%" height="100%" minWidth={0} minHeight={200} aspect={undefined}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={30}
            outerRadius={45}
            paddingAngle={5}
            dataKey="value"
          >
            <Cell fill={COLORS.primary} />
            <Cell fill="#ffffff10" />
          </Pie>
          <Tooltip contentStyle={{ background: '#050505', border: '1px solid #1A1A1A' }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
};
